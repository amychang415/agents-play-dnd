import os
import random
import io
import csv
from llm_utils import *
from agents import agent_list
from plans import *

class Agent:
    def __init__(self, name, persona):
        self.name = name
        self.persona = persona
        self.char_options = []
        self.character = Character()
        self.actions = []

class Character:
    def __init__(self):
            self.name = ""
            self.background = ""
            self.my_class = ""
            self.race = ""
            self.stats = ""
            self.skills = ""

class Game:
    def __init__(self, agent_list, base_senario):
        self.agents = agent_list # list of Agents
        self.dead_agents = [] # any dead agents go here
        self.gamestate = "setup" # current state of the game
        self.game_log = "Nothing has been said yet. Start the conversation."
        self.day_log = ""
        self.all_messages = []
        self.senario = base_senario # background info
        self.num_rounds = 0

    def conduct_interviews(self, filename):
        """Conduct interviews with each agent and export their answers to a CSV."""
        data = []
        for agent in self.agents + self.dead_agents:
            for other_agent in self.agents + self.dead_agents:
                if agent != other_agent:
                    # Prompt the agent with questions about the other agent
                    questions = f"""
                    You have finished playing a DnD campaign. Here are some questions:
                    1. How positive or negative is your view of {other_agent.name} as a player? Please rate on a 1-10 scale where 10 is very positive. Why?
                    2. How well do you think {other_agent.name} contributed to the team? Please rate on a 1-10 scale where 10 is very positive. Why?
                    3. Would you like to play with {other_agent.name} again? Please rate on a 1-10 scale where 10 is you would be very exctied to. Why?

                    Respond briefly for each question in JSON format as:
                    {{
                        "impression": "Your impression of the other player on 1-10 scale",
                        "contribution": "How well the other player contributed on a 1-10 scale",
                        "play_again": "Would you play with them again on a 1-10 scale"
                    }}
                    """
                    response = self.prompt_agent(agent, questions)
                    answers = parse_json(response)

                    data.append({
                        "Agent Name": agent.name,
                        "Other Agent": other_agent.name,
                        "Impression": answers.get("impression", "No response"),
                        "Contribution": answers.get("contribution", "No response"),
                        "Play Again": answers.get("play_again", "No response"),
                    })

        # Write interview data to CSV
        with open(filename, mode="w", newline="", encoding="utf-8") as csvfile:
            fieldnames = ["Agent Name", "Other Agent", "Impression", "Contribution", "Play Again"]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)

        print(f"Interview results exported to {filename}.")

    def export_to_csv(self, filename):
        # Collect data for CSV
        data = []
        # Include created characters
        for agent in self.agents + self.dead_agents:
            for char in agent.char_options:
                data.append({
                    "Agent Name": agent.name,
                    "Character Name": char.name,
                    "Character Race": char.race,
                    "Character Class": char.my_class,
                    "Character Background": char.background,
                    "Character Stats": char.stats,
                    "Character Skills": char.skills,
                    "Party Members": "N/A",
                    "Action": "Created Character",
                    "Roll Type": "N/A",
                    "Roll Number": "N/A",
                    "Roll Advantage": "N/A",
                    "Roll Result": "N/A",
                })
        
        #includes actions taken
        for agent in self.agents + self.dead_agents:
            for action_entry in getattr(agent, "actions", []):
                data.append({
                    "Agent Name": agent.name,
                    "Character Name": agent.character.name,
                    "Character Race": agent.character.race,
                    "Character Class": agent.character.my_class,
                    "Character Background": agent.character.background,
                    "Character Stats": agent.character.stats,
                    "Character Skills": agent.character.skills,
                    "Party Members": ", ".join([member.name for member in self.agents if member != agent]),
                    "Action": action_entry.get("action"),
                    "Roll Type": action_entry.get("roll_type"),
                    "Roll Number": action_entry.get("roll_num"),
                    "Roll Advantage": action_entry.get("roll_advantage"),
                    "Roll Result": action_entry.get("roll_result"),
                })

        # Write to CSV
        with open(filename, mode="w", newline="", encoding="utf-8") as csvfile:
            fieldnames = ["Agent Name", "Character Name", "Character Race", "Character Class",
                          "Character Background", "Character Stats", "Character Skills",
                          "Party Members", "Action", "Roll Type", "Roll Number", "Roll Advantage", "Roll Result"]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)

        print(f"Game summary exported to {filename}.")
    
    # Prompt the llm as one of the agents
    def prompt_agent(self, agent, instruction):
        # get the custom prompt per agent
        prompt = self._create_agent_prompt(agent)
        messages = [
            {"role": "system", "content": prompt}, # General prompt
            {"role": "user", "content": self.game_log}, # Everything that's been said so far
            {"role": "system", "content": instruction} # What we want the agent to do
        ]
        response = gen_oai(messages)
        return response
    
    # Prompt the DM with an agent and the action they want to make.
    def prompt_dm_roll(self, agent, action):
        prompt = self._create_dm_prompt()

        roll_num = random.randint(1,20)
        instruction = self._roll_instruction(agent, action, roll_num)
        messages = [
            {"role": "system", "content": prompt}, # General prompt
            {"role": "user", "content": self.game_log}, # Everything that's been said so far
            {"role": "system", "content": instruction} # What we want the agent to do
        ]

        roll = parse_json(gen_oai(messages))

        roll_type = roll.get("type")
        roll_advantage = roll.get("advantage")
        roll_result = roll.get("result")

        # update game log
        self._update_game_log("DM", f"{roll_type} with {roll_advantage}, {roll_num}: {roll_result}")

        agent.actions.append({
            "action": action,
            "roll_type": roll_type,
            "roll_advantage": roll_advantage,
            "roll_num": roll_num,
            "roll_result": roll_result,
        })

    def prompt_dm_general(self, instruction):
        prompt = self._create_dm_prompt()

        messages = [
            {"role": "system", "content": prompt}, # General prompt
            {"role": "user", "content": self.game_log}, # Everything that's been said so far
            {"role": "system", "content": instruction} # What we want the agent to do
        ]
        response = gen_oai(messages)
        self._update_game_log("DM", response)
        return response

    # Called every time an agent speaks to update the game's log
    def _update_game_log(self, name, message):
        self.all_messages.append(f"{name}: {message}")
        print(f"{name}: {message}")
        self.game_log += f"{name}: {message}"

    # called to see what roll a player should make to complete their action. Rolls d20
    def _roll_instruction(self, agent, action, num):

        instruction = f"""
        Player {agent.name} wants to {action}. What roll should they make? 
        
        The possible roll types are: 
        1) stat checks for constitution, strength, dexterity, intelligence, wisdom, or charisma,  
        2) saving throws for constitution, strength, dexterity, intelligence, wisdom, or charisma, 
        3) skill checks for athletics, acrobatics, sleight of hand, stealth, arcana, history, investigation, nature, religion, animal handling, insight, medicine, perception, survival, deception, intimidation, performance, or persuasion
        5) attack check

        Should they roll with advantage, disadvantage, or normal?

        They rolled {num} out of 20. Higher numbers are better. Remember that the character taking this action is {agent.character.name}, a {agent.character.race} {agent.character.my_class} with {agent.character.skills} and {agent.character.stats}. What happens?

        No prose. Respond only in JSON using the following format: "type": skill check for athletics/stat check for strength/etc , "advantage": advatnage/disadvantage/normal, "result": explanation of what happens
        """
        return instruction

    # the prompt for the DM, including the detailed campaign plans
    def _create_dm_prompt(self):
        prompt = f"""
        YOU: You are the dungeon master for a Dungeon and Dragons campaign. You are directing a campaign.

        STYLE: Speak to the players directly. Do not append your name to the response. Only respond with what you would say. You want to move the plot along according to your campaign plans. Be concise, but creative! No emojis.

        SCENARIO: The players know that the senario for this campaign is: {self.senario}. Your detailed campaign plans, which the players do not know, are: {plan}. Don't reveal any details that the players have not explored on their own.
        """
        return prompt

    # General prompt, custom per agent
    def _create_agent_prompt(self, agent):
        prompt = f"""
        YOU: You are {agent.name}, {agent.persona}. Speak in character as {agent.name} with very short messages in a conversational tone. Do not repeat yourself.

        STYLE: Speak casually and in your own personal voice. Do not append your name to the response. Only respond with what you would say. Speak in very short messages, but be creative! Speak only as yourself. No emojis.

        SCENARIO: You are playing Dungeons and Dragons (DnD) with a group of people containing {', '.join(a.name for a in self.agents)}. The background for the game you are playing is: {senario}
        """

        if agent.character.name:
            prompt += f"CHARACTER: Your Dungeons and Dragons character is {agent.character.name}, a {agent.character.race} {agent.character.my_class} with {agent.character.skills} and {agent.character.stats}. Their background is {agent.character.background}."
        
        return prompt

    # Each agent creates one character
    def create_char(self):
        instructions = self._character_creation_instructions()
        for agent in self.agents:
            response = self.prompt_agent(agent, instructions)

            # dict with the character's info
            char = parse_json(response)

            # turn that dict into an object
            potential_char = Character()
            potential_char.name = char.get("name")
            potential_char.background = char.get("background")
            potential_char.my_class = char.get("class")
            potential_char.race = char.get("race")
            potential_char.stats = char.get("stats")
            potential_char.skills = char.get("skills")
        
            self._update_game_log(agent.name, f"Creates {potential_char.name}, {potential_char.background} {potential_char.name} is a {potential_char.race} {potential_char.my_class} with {potential_char.skills} and {potential_char.stats}.")
            agent.char_options.append(potential_char)

    # instructions for how to create a character, including JSON format
    def _character_creation_instructions(self):
        instructions = f"""
        Create a DnD character you would like to play as, which has a name, class, race, and backstory. Make your character unique!
        
        The possible races are: Human, Elf, Halfling, Dwarf, Tiefling. 
        
        The possible classes are: {class_info}

        Based on the backstory, pick of three of the following skills for your character to have proficency in: {skills_info}

        Based on the backstory, assign one of [16, 14, 14, 12, 10, 8] to each of your character's 6 core stats. These 6 core stats are {stats_info}.
        
        No prose, response only in JSON using the following format: "name": name of character, "race": race of character, "class": class of character, "background": background of character, "skills": skills of character, "stats": stats of character"
        """
        return instructions

    # choosing one of three characters
    def choose_chars(self):
        random.shuffle(self.agents)
        for i in range(3):
            for agent in self.agents:
                discuss = self.prompt_agent(agent, "Discuss in the group which of the three DnD characters each person should play as. Each person can only play as a character they created themselves.")
                self._update_game_log(agent.name, discuss)

        for agent in self.agents:
            choice = self.prompt_agent(agent, f"""Choose one of the three characters you created to play as. No prose, respond only in JSON using the following format: "name": name of character, "race": race of character, "class": class of character, "background": background of character, "skills": skills of character, "stats": stats of character""")
            char = parse_json(choice)

            # putting info into empty character object
            agent.character.name = char.get("name")
            agent.character.background = char.get("background")
            agent.character.my_class = char.get("class")
            agent.character.race = char.get("race")
            agent.character.stats = char.get("stats")
            agent.character.skills = char.get("skills")

            self._update_game_log(agent.name, f"Chooses to play as {agent.character.name}")
    
    def play_round(self):
        self.num_rounds += 1
        self.game_log = self.day_log

        self.prompt_dm_general("What happens next? Move the plot along, but don't reveal any details that the players have not explored on their own.")
        for i in range(2):
            random.shuffle(self.agents)
            for agent in self.agents:
                discuss = self.prompt_agent(agent, "Discuss what to do next in the game.")
                self._update_game_log(agent.name, discuss)
        for agent in self.agents:
                action = self.prompt_agent(agent, "Choose an action for your DnD character to perform next. This is one simple action that can be completed withing the character's immediate surroundings.")
                self._update_game_log(agent.name, action)
                # resolve the action
                self.prompt_dm_roll(agent, action)

        # at the end of the round, check if the game has ended
        self.check_game_state()

        # next round, start with only a summary of previous rounds
        self.day_log += self.summarize_round(self.game_log, self.num_rounds)

    # checks if the game has ended
    def check_game_state(self):
        # Prepare the prompt to evaluate the game state
        state_prompt = """
        This DnD campaign should end when the wolves have been defeated or the players have reached a settlement with the wolves and the town.

        Based on the following game log, determine if the game should end.
        
        If the game should end, return a JSON response in the following format: "game_concluded": true
        
        Otherwise, respond with: "game_concluded": false
        """
        response = gen_oai([{"role": "system", "content": state_prompt},
                            {"role": "user", "content": self.game_log}])
        

        # Parse the response
        state_info = parse_json(response)
        game_concluded = state_info.get("game_concluded")

        self._update_game_log("System", game_concluded)

        # Return whether the game has concluded based on the LLM's analysis
        if game_concluded:
            self._update_game_log("System", "The game has ended.")
            self.gamestate = "finished"
            return True
        
        return False

    # summarize a round of DnD
    def summarize_round(self, log, num):
        summary_prompt = f"""
        Summarize what happened in this game round. 
        Only summarize information from the most recent round. 
        Leave in key events and important character decisions. 
        Keep detail in the most recent actions. Keep detail in the current context, such as the player's location and other characters present.
        """

        prompt = self._create_dm_prompt()

        messages = [
            {"role": "system", "content": prompt}, # General prompt
            {"role": "user", "content": log}, # Day log
            {"role": "system", "content": summary_prompt} # What we want the agent to do
        ]
        summary = gen_oai(messages)
        
        # Return the summary
        print(f"ROUND {num} \n{summary}\nEND OF ROUND {num}.\n")
        return f"ROUND {num} \n{summary}\nEND OF ROUND {num}.\n"

    def export_messages_to_csv(self, group_number):
        """
        Export all messages into a CSV file named "group_<group_number>_all_messages_two.csv".

        :param group_number: The group number to include in the file name.
        """
        filename = f"group_{group_number}_all_messages_two12333.csv"
        
        # Define the CSV header
        headers = ["message"]
        
        try:
            # Write messages to the CSV file
            with open(filename, mode="w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                
                # Write the header row
                writer.writerow(headers)
                
                # Write each message as a row
                for message in self.all_messages:
                    writer.writerow([message])  # Wrap message in a list for a single column
                
            print(f"Messages successfully exported to {filename}")
        except Exception as e:
            print(f"An error occurred while exporting messages: {e}")



if __name__ == "__main__":
    senario = """The region surrounding Welton is a quiet and pastoral land, where small, self-reliant villages are scattered across rolling hills and dense forests. For years, the people of these villages have enjoyed a relatively peaceful existence, with their concerns limited to the cycles of planting and harvest or the occasional minor squabble among neighbors. Life in this part of the world moves slowly, and the townsfolk place their faith in hard work, tradition, and their local leaders. However, beneath the surface of this idyllic setting lies a tension—ancient woods, whispered to hold secrets of the arcane, stretch out beyond the farmlands, a boundary that the villagers rarely cross.
Welton, perched on the edge of these woods, is a picturesque settlement with white-walled cottages and a bustling community of farmers, shepherds, and traders. But the calm has been shattered. Wolves, far more cunning and organized than the villagers have ever encountered, are attacking farms and driving families from their homes. The people’s protector, a local sorcerer, has mysteriously vanished, leaving Welton vulnerable. Now, food supplies dwindle, and the village faces ruin unless something is done. The call for help has gone out: Welton offers a generous reward to any who can rid them of this menace. Whether you come to answer that call or simply pass through, Welton and its dark woods beckon, hiding a mystery that could change everything. Will you uncover the truth or fall prey to the wilderness?
"""
    group_num = 1
    for persona_group in agents_list:
        initialized_agents = [Agent(agent_data["name"], agent_data["persona"]) for agent_data in persona_group]
    
        game = Game(initialized_agents, senario)

        game.create_char()
        game.create_char()
        game.create_char()
        game.choose_chars()
        game.gamestate = "playing"

        rounds_num = 0

        while game.gamestate != "finished":
            game.play_round()
            rounds_num += 1

            if rounds_num >= 25:
                game.gamestate = "finished"

        game.export_messages_to_csv(group_num)
        game.export_to_csv(f"group_{group_num}_data_two")
        game.conduct_interviews(f"group_{group_num}_interviews_two")

        group_num += 1
