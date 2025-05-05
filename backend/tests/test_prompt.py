from backend import prompt


initial_predict_template = prompt.INITIAL_PREDICTION_PROMPT
final_preddict_template = prompt.FINAL_PREDICTION_INSTRUCTION

# Example: You would format it with actual data when needed
match_data_example = {'home_team': 'Arsenal', 'away_team': 'Man Utd'}
parameters = {'number_of_predicted_events': 15}
formatted_initial_prompt = initial_predict_template.format(
    home_team=match_data_example.get('home_team', 'Unknown Home Team'),
    away_team=match_data_example.get('away_team', 'Unknown Away Team'),
number_of_predicted_events=parameters.get('number_of_predicted_events')
)

formatted_final_instruction = final_preddict_template.format(
    home_team=match_data_example.get('home_team', 'Unknown Home Team'),
    away_team=match_data_example.get('away_team','Unknown Away Team')
)

print("Here is the formatted prompt template:")
print(formatted_initial_prompt)
print('--------------------------------------')
print(formatted_final_instruction)

