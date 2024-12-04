from openai import OpenAI
import json
import re
from plans import *
import tiktoken

from settings import *
oai = OpenAI(api_key = OPENAI_API_KEY)
gpt = "gpt-4o"

def gen_oai(messages):
  max_tokens = 8000  # Safe limit for GPT-3.5-tubro-16k
  max_completion_tokens = 1500  # Tokens reserved for the response
  token_budget = max_tokens - max_completion_tokens  # Tokens available for the input

  # Ensure the input messages fit within the token budget
  messages = ensure_messages_fit(messages, token_budget)

  response = oai.chat.completions.create(
    model=gpt,
    temperature=0.7,
    messages=messages,
    max_completion_tokens= 1500
  )
  content = response.choices[0].message.content
  return content

def ensure_messages_fit(messages, token_budget):
  """
  Ensure the input messages fit within the specified token budget.
  Truncate or summarize only the user messages, preserving assistant and system messages.
  """
  # Separate system, assistant, and user messages
  system_messages = [msg for msg in messages if msg["role"] == "system"]
  assistant_messages = [msg for msg in messages if msg["role"] == "assistant"]
  user_messages = [msg for msg in messages if msg["role"] == "user"]

  # Calculate token counts
  system_tokens = calculate_total_tokens(system_messages)
  assistant_tokens = calculate_total_tokens(assistant_messages)
  total_tokens = calculate_total_tokens(messages)

  # If already within budget, return the original messages
  if total_tokens <= token_budget:
      return messages

  # Determine remaining budget for user messages
  max_tokens_for_user = token_budget - system_tokens - assistant_tokens
  if max_tokens_for_user <= 0:
      raise ValueError("System and assistant messages alone exceed the token budget!")

  # Truncate user messages to fit within the budget
  enc = tiktoken.encoding_for_model(gpt)
  truncated_user_messages = []

  current_tokens = 0
  for msg in user_messages:
      sanitized_content = sanitize_prompt(msg["content"])  # Sanitize before tokenization
      message_tokens = len(enc.encode(sanitized_content))
      if current_tokens + message_tokens > max_tokens_for_user:
          # Truncate message to fit remaining budget
          remaining_tokens = max_tokens_for_user - current_tokens
          truncated_content = enc.decode(enc.encode(sanitized_content)[:remaining_tokens])
          truncated_user_messages.append({"role": msg["role"], "content": truncated_content})
          break
      else:
          truncated_user_messages.append({"role": msg["role"], "content": sanitized_content})
          current_tokens += message_tokens

  # Combine system, assistant, and truncated user messages
  adjusted_messages = system_messages + assistant_messages + truncated_user_messages
  return adjusted_messages

# parses json, regex failback
def parse_json(response, target_keys=None):
  json_start = response.find('{')
  json_end = response.rfind('}') + 1
  cleaned_response = response[json_start:json_end].replace('\\"', '"')
  
  try:
    parsed = json.loads(cleaned_response)
    if target_keys:
      parsed = {key: parsed.get(key, "") for key in target_keys}
    return parsed
  except json.JSONDecodeError:
    #print("Tried to parse json, but it failed. Switching to regex fallback.")
    #print(f"Response: {cleaned_response}")
    parsed = {}
    for key_match in re.finditer(r'"(\w+)":\s*', cleaned_response):
      key = key_match.group(1)
      if target_keys and key not in target_keys:
        continue
      value_start = key_match.end()
      if cleaned_response[value_start] == '"':
        value_match = re.search(r'"(.*?)"(?:,|\s*})', 
                                cleaned_response[value_start:])
        if value_match:
          parsed[key] = value_match.group(1)
      elif cleaned_response[value_start] == '{':
        nested_json = re.search(r'(\{.*?\})(?:,|\s*})', 
                                cleaned_response[value_start:], re.DOTALL)
        if nested_json:
          try:
            parsed[key] = json.loads(nested_json.group(1))
          except json.JSONDecodeError:
            parsed[key] = {}
      else:
        value_match = re.search(r'([^,}]+)(?:,|\s*})', 
                                cleaned_response[value_start:])
        if value_match:
          parsed[key] = value_match.group(1).strip()
    
    if target_keys:
      parsed = {key: parsed.get(key, "") for key in target_keys}
    return parsed

# takes dict
def calculate_total_tokens(messages):
  total_tokens = 0
  for message in messages:
      if "content" in message:
          sanitized_content = sanitize_prompt(message["content"])  # Sanitize here
          total_tokens += estimate_tokens(sanitized_content)
  return total_tokens

#only takes a string
def estimate_tokens(text):
  if not text:
    return 0
  enc = tiktoken.encoding_for_model(gpt)
  return len(enc.encode(text))  # uses tiktoken to count token number in text

def sanitize_prompt(prompt):
  enc = tiktoken.encoding_for_model(gpt)
  sanitized_prompt = enc.decode(enc.encode(prompt))
  return sanitized_prompt
