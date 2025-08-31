import copy

class State:

    SERVE='Serve'
    SERVE_1='A'
    SERVE_2='B'
    SERVE_NONE='None'
    T1TIMEOUTS_INT='Team 1 Timeouts'
    T2TIMEOUTS_INT='Team 2 Timeouts'
    T1SETS_INT='Team 1 Sets'
    T2SETS_INT='Team 2 Sets'
    CURRENT_SET_INT='Current Set'
    T1SET1_INT='Team 1 Game 1 Score'
    T1SET2_INT='Team 1 Game 2 Score'
    T1SET3_INT='Team 1 Game 3 Score'
    T1SET4_INT='Team 1 Game 4 Score'
    T1SET5_INT='Team 1 Game 5 Score'
    T2SET1_INT='Team 2 Game 1 Score'
    T2SET2_INT='Team 2 Game 2 Score'
    T2SET3_INT='Team 2 Game 3 Score'
    T2SET4_INT='Team 2 Game 4 Score'
    T2SET5_INT='Team 2 Game 5 Score'

    reset_model = {
                SERVE: SERVE_NONE,
                T1SETS_INT: '0',
                T2SETS_INT: '0',
                T1SET1_INT: '0',
                T1SET2_INT: '0',
                T1SET3_INT: '0',
                T1SET4_INT: '0',
                T1SET5_INT: '0',
                T2SET1_INT: '0',
                T2SET2_INT: '0',
                T2SET3_INT: '0',
                T2SET4_INT: '0',
                T2SET5_INT: '0',
                T1TIMEOUTS_INT: '0',
                T2TIMEOUTS_INT: '0',
                CURRENT_SET_INT: 1
                }
    

    def keys_to_reset_simple_mode():
        return {State.T1SET5_INT,
                State.T2SET5_INT,
                State.T1SET4_INT,
                State.T2SET4_INT,
                State.T1SET3_INT,
                State.T2SET3_INT,
                State.T1SET2_INT,
                State.T2SET2_INT, 
                State.T1SET1_INT,
                State.T2SET1_INT}
    

    def __init__(self, new_state = None):
        if new_state == None:
            self.current_model = copy.copy(self.reset_model)
        else:
            self.current_model = new_state
            self.current_model[State.CURRENT_SET_INT] = '1'

    
    def get_reset_model(self):
        return self.reset_model.copy()
    
    def get_current_model(self):
        return self.current_model
    
    def set_current_set(self, set):
        self.current_model[State.CURRENT_SET_INT]=set

    def simplify_model(simplified): 
        current_set = simplified[State.CURRENT_SET_INT]
        t1_points = simplified[f'Team 1 Game {current_set} Score']
        t2_points = simplified[f'Team 2 Game {current_set} Score']
        for key in State.keys_to_reset_simple_mode():
            if key in simplified:
                simplified[key] = '0'
            
        simplified[State.T1SET1_INT] = t1_points
        simplified[State.T2SET1_INT] = t2_points
        return simplified
    
    def get_timeout(self, team):
        return int(self.current_model[f'Team {team} Timeouts'])
    
    def set_timeout(self, team, value):
        self.current_model[f'Team {team} Timeouts'] = str(value)

    def get_sets(self, team):
        return int(self.current_model[f'Team {team} Sets'])
    
    def set_sets(self, team, value):
        self.current_model[f'Team {team} Sets'] = str(value)
    
    def get_game(self, team, set):
        return int(self.current_model[f'Team {team} Game {set} Score']) 

    def set_game(self, set, team, value):
        self.current_model[f'Team {team} Game {set} Score'] = str(value)

    def set_current_serve(self, value):
        self.current_model[State.SERVE] = value

    def get_current_serve(self):
        return self.current_model[State.SERVE]
    