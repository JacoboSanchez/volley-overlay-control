import copy

class State:

    SERVE='Serve'
    SERVE_1='A'
    SERVE_2='B'
    SERVE_NONE='None'
    LOGOS_BOOL='logos'
    T1TIMEOUTS_INT='team1timeouts'
    T2TIMEOUTS_INT='team2timeouts'
    T1SETS_INT='T1 Sets'
    T2SETS_INT='T2 Sets'
    CURRENT_SET_INT='Current Set'
    T1SET1_INT='T1G1'
    T1SET2_INT='T1G2'
    T1SET3_INT='T1G3'
    T1SET4_INT='T1G4'
    T1SET5_INT='T1G5'
    T2SET1_INT='T2G1'
    T2SET2_INT='T2G2'
    T2SET3_INT='T2G3'
    T2SET4_INT='T2G4'
    T2SET5_INT='T2G5'
    A_TEAM = 'a1Team'
    B_TEAM = 'b1Team'

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
    

    def getKeysToReset():
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

    
    def getResetModel(self):
        return self.reset_model
    
    def getCurrentModel(self):
        return self.current_model
    
    def getCurrentModelValue(self, value):
        return self.current_model[value]
    
    def setCurrentSet(self, set):
        self.current_model[State.CURRENT_SET_INT]=set

    def simplifyModel(simplified): 
        current_set = simplified[State.CURRENT_SET_INT]
        t1_points = simplified[f'T1G{current_set}']
        t2_points = simplified[f'T2G{current_set}']
        for key in State.getKeysToReset():
            if key in simplified:
                simplified[key] = '0'
            
        simplified[State.T1SET1_INT] = t1_points
        simplified[State.T2SET1_INT] = t2_points
        return simplified
    
    def getTimeout(self, team):
        return int(self.current_model[f'team{team}timeouts'])
    
    def setTimeout(self, team, value):
        self.current_model[f'team{team}timeouts'] = str(value)

    def getSets(self, team):
        return int(self.current_model[f'T{team} Sets'])
    
    def setSets(self, team, value):
        self.current_model[f'T{team} Sets'] = str(value)
    
    def getGame(self, team, set):
        return int(self.current_model[f'T{team}G{set}']) 

    def setGame(self, set, team, value):
        self.current_model[f'T{team}G{set}'] = str(value)

    def setCurrentServe(self, value):
        self.current_model[State.SERVE] = value

    def getCurrentServe(self):
        return self.current_model[State.SERVE]
    
    def getTeamName(self, team):
        if (team == 1):
            return self.current_model[State.A_TEAM]
        return self.current_model[State.B_TEAM]
        
        return self.current_model[f'a{team}Team']
    
    def setTeamName(self, team, name):
        if (team == 1):
            self.current_model[State.A_TEAM] = name
        else:
            self.current_model[State.B_TEAM] = name
    
    def isShowLogos(self):
        return self.current_model[State.LOGOS_BOOL]
    
    def setShowLogos(self, value):
        self.current_model[State.LOGOS_BOOL] = value
    