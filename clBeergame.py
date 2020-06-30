import time
from time import gmtime, strftime
import numpy as np
import random
from random import randint
from clAgent import Agent
from plotting import plotting, savePlot, plotBaseStock
import matplotlib.pyplot as plt
import os 
from matplotlib import rc
rc('text', usetex=True)
import tensorflow as tf 
from collections import deque 

class clBeerGame(object):
	def __init__(self, config):
		self.config = config
		self.curGame = 0 # The number associated with the current game (counter of the game)
		self.curTime = 0
		self.totIterPlayed = 0  # total iterations of the game, played so far in this and previous games
		self.players = self.createAgent()  # create the agents 
		self.T = 0
		self.demand = []
		self.playType = []  # "train" or "test"
		self.ifOptimalSolExist = self.config.ifOptimalSolExist
		self.getOptimalSol()
		self.totRew = 0    # it is reward of all players obtained for the current player.
		self.resultTest	= []
		self.runnerMidlResults = []		# stores the results to use in runner comparisons
		self.runnerFinlResults = []		# stores the results to use in runner comparisons
		self.middleTestResult = []		# stores the whole middle results of optm, frmu, and random to avoid doing same tests multiple of times.
		self.runNumber = 0		# the runNumber which is used when use runner
		self.strNum = 0			# the runNumber which is used when use runner		
		
	# createAgent : Create agent objects (agentNum,IL,OO,c_h,c_p,type,config)
	def createAgent(self): 	
		agentTypes = self.config.agentTypes 
		return [Agent(i,self.config.ILInit[i], self.config.AOInit, self.config.ASInit[i], 
                              self.config.c_h[i], self.config.c_p[i], self.config.eta[i], 
                              agentTypes[i],self.config) for i in range(self.config.NoAgent)]
			
	# planHorizon : Find a random planning horizon
	def planHorizon(self):
		# TLow: minimum number for the planning horizon # TUp: maximum number for the planning horizon
		#output: The planning horizon which is chosen randomly.
		return randint(self.config.TLow,self.config.TUp)

	# this function resets the game for start of the new game
	def resetGame(self, demand, playType):
		self.playType = playType  #"train" or "test"
		self.demand = demand
		self.curTime = 0
		if playType == "train":
			self.curGame += 1
			self.totIterPlayed += self.T
			self.T = self.planHorizon()	
		else:
			self.T = self.config.Ttest	
			
		# reset the required information of player for each episode
		for k in range(0,self.config.NoAgent):
			self.players[k].resetPlayer(self.T)

		# update OO when there are initial IL,AO,AS
		self.update_OO()
	
	# correction on cost at time T according to the cost of the other players
	def getTotRew(self):
		totRew = 0
		for i in range(self.config.NoAgent):
			# sum all rewards for the agents and make correction
			totRew += self.players[i].cumReward

		for i in range(self.config.NoAgent):
			self.players[i].curReward += self.players[i].eta*(totRew - self.players[i].cumReward) #/(self.T)
	
	# make correction to the rewards in the experience replay for all iterations of current game
	def distTotReward(self):
		totRew = 0
		optRew = 0.1
		for i in range(self.config.NoAgent):
			# sum all rewards for the agents and make correction
			totRew += self.players[i].cumReward	
		totRew += optRew
		
		for i in range(self.config.NoAgent):
			for j in range(self.T):
				if self.config.NoAgent>1 and hasattr(self.players[i], 'brain') and (len(self.players[i].brain.replayMemory)>0):
					#self.players[i].brain.replayMemory[-1*(j+1)][2] += (np.power(self.config.alpha,j)/(self.config.NoAgent-1))*((totRew - self.players[i].cumReward)/(self.T)) # changes the last T periods in the replayMemory
					self.players[i].brain.replayMemory[-1*(j+1)][2] += (self.config.distCoeff/(self.config.NoAgent-1))*((totRew - self.players[i].cumReward)/(self.T)) # changes the last T periods in the replayMemory					

	def getAction(self, k):
		
		# get action for training run
		if self.playType == "train":
			if  self.players[k].compTypeTrain == "dnn":
				self.players[k].action = np.zeros(self.config.actionListLen)
				self.players[k].action = self.players[k].brain.getDNNAction(self.playType)
			elif self.players[k].compTypeTrain == "frmu":
				self.players[k].action = np.zeros(self.config.actionListLenOpt)
				self.players[k].action[np.argmin(np.abs(np.array(self.config.actionListOpt)\
									-max(0,round(self.players[k].AO[self.curTime] +\
									self.players[k].alpha_b*(self.players[k].IL - self.players[k].a_b) +\
									self.players[k].betta_b*(self.players[k].OO - self.players[k].b_b)))))] = 1
			elif self.players[k].compTypeTest == "rnd":	
				self.players[k].action = np.zeros(self.config.actionListLen)
				a = np.random.randint(self.config.actionListLen)
				self.players[k].action[a] = 1
			elif self.players[k].compTypeTrain == "optm":	
				self.players[k].action = np.zeros(self.config.actionListLenOpt)
				if self.config.demandDistribution == 2:
					if self.curTime   and self.config.use_initial_BS <= 4:
						self.players[k].action [np.argmin(np.abs(np.array(self.config.actionListOpt)-\
								max(0,(self.players[k].init_optmlBaseStock - (self.players[k].IL + self.players[k].OO - self.players[k].AO[self.curTime]))) ))] = 1	
					else: 
						self.players[k].action [np.argmin(np.abs(np.array(self.config.actionListOpt)-\
								max(0,(self.players[k].optmlBaseStock - (self.players[k].IL + self.players[k].OO - self.players[k].AO[self.curTime]))) ))] = 1	
				else:
					self.players[k].action [np.argmin(np.abs(np.array(self.config.actionListOpt)-\
								max(0,(self.players[k].optmlBaseStock - (self.players[k].IL + self.players[k].OO - self.players[k].AO[self.curTime]))) ))] = 1	
			else:
				# not a valid player is defined.
				raise Exception('The player type is not defined or it is not a valid type.!')

		# get action for test runs
		elif self.playType == "test":
			if  self.players[k].compTypeTest == "dnn":
				self.players[k].action = np.zeros(self.config.actionListLen)
				if self.config.ifPlaySavedData:
					self.players[k].action[int(self.loaded_dqn_actions[self.curTime])] = 1
				else:
					self.players[k].action = self.players[k].brain.getDNNAction(self.playType)
			elif self.players[k].compTypeTest == "frmu":
				self.players[k].action = np.zeros(self.config.actionListLenOpt)

				self.players[k].action[np.argmin(np.abs(np.array(self.config.actionListOpt)-\
								max(0,round(self.players[k].AO[self.curTime] +\
									self.players[k].alpha_b*(self.players[k].IL - self.players[k].a_b) +\
									self.players[k].betta_b*(self.players[k].OO - self.players[k].b_b)))))] = 1	
			elif self.players[k].compTypeTest == "rnd":	
				self.players[k].action = np.zeros(self.config.actionListLen)
				a = np.random.randint(self.config.actionListLen)
				self.players[k].action[a] = 1
			elif self.players[k].compTypeTest == "optm":
				self.players[k].action = np.zeros(self.config.actionListLenOpt)

				if self.config.demandDistribution == 2:
					if self.curTime   and self.config.use_initial_BS <= 4:
						self.players[k].action [np.argmin(np.abs(np.array(self.config.actionListOpt)-\
								max(0,(self.players[k].init_optmlBaseStock - (self.players[k].IL + self.players[k].OO - self.players[k].AO[self.curTime]))) ))] = 1	
					else: 
						self.players[k].action [np.argmin(np.abs(np.array(self.config.actionListOpt)-\
								max(0,(self.players[k].optmlBaseStock - (self.players[k].IL + self.players[k].OO - self.players[k].AO[self.curTime]))) ))] = 1	
				else:
					self.players[k].action [np.argmin(np.abs(np.array(self.config.actionListOpt)-\
								max(0,(self.players[k].optmlBaseStock - (self.players[k].IL + self.players[k].OO - self.players[k].AO[self.curTime]))) ))] = 1	
			else:
				# not a valid player is defined.
				raise Exception('The player type is not defined or it is not a valid type.!')
              	# print(self.curTime, self.players[k].agentNum, "IL", self.players[k].IL, "OO", self.players[k].OO, "Op", self.players[k].optmlBaseStock, self.players[k].optmlBaseStock - (self.players[k].IL + self.players[k].OO))
	
	# next action
	def next(self):
		# get a random leadtime		
		leadTimeIn = randint(self.config.leadRecItemLow[self.config.NoAgent-1], self.config.leadRecItemUp[self.config.NoAgent-1]) 
		# handle the most upstream recieved shipment 		
		self.players[self.config.NoAgent-1].AS[self.curTime + leadTimeIn] += self.players[self.config.NoAgent-1].actionValue(self.curTime, self.playType)

		for k in range(self.config.NoAgent-1,-1,-1): # [3,2,1,0]
			
			# get current IL and Backorder
			current_IL = max(0, self.players[k].IL)
			current_backorder = max(0, -self.players[k].IL)

			# TODO: We have get the AS and AO from the UI and update our AS and AO, so that code update the corresponding variables
			
			# increase IL and decrease OO based on the action, for the next period 
			self.players[k].recieveItems(self.curTime)
			
			# observe the reward
			possible_shipment = min(current_IL + self.players[k].AS[self.curTime], current_backorder + self.players[k].AO[self.curTime])
			
			# plan arrivals of the items to the downstream agent
			if self.players[k].agentNum > 0:
				leadTimeIn = randint(self.config.leadRecItemLow[k-1], self.config.leadRecItemUp[k-1])
				self.players[k-1].AS[self.curTime + leadTimeIn] += possible_shipment

			# update IL
			self.players[k].IL -= self.players[k].AO[self.curTime]
			# observe the reward
			self.players[k].getReward()
			self.players[k].hist[-1][-2] = self.players[k].curReward
			self.players[k].hist2[-1][-2] = self.players[k].curReward

			# update next observation 
			self.players[k].nextObservation = self.players[k].getCurState(self.curTime+1)
		
		if self.config.ifUseTotalReward:
			# correction on cost at time T
			if self.curTime == self.T:
				self.getTotRew()					
		
		self.curTime +=1				
	
	def handelAction(self):
		# get random lead time 
		leadTime = randint(self.config.leadRecOrderLow[0], self.config.leadRecOrderUp[0])
		# set AO 
		self.players[0].AO[self.curTime] += self.demand[self.curTime]
		for k in range(0,self.config.NoAgent): 
			self.getAction(k)
			
			self.players[k].dnnBaseStock += [self.players[k].actionValue( \
				self.curTime, self.playType) + self.players[k].IL + self.players[k].OO]
			
			# update hist for the plots	
			self.players[k].hist += [[self.curTime,self.players[k].IL, self.players[k].OO,\
						self.players[k].actionValue(self.curTime,self.playType),self.players[k].curReward, self.players[k].dnnBaseStock[-1]]]

			if (self.players[k].compTypeTrain == "dnn" and self.playType == "train") or (self.players[k].compTypeTest == "dnn" and self.playType == "test"):
				self.players[k].hist2 += [[self.curTime,self.players[k].IL, self.players[k].OO, self.players[k].AO[self.curTime], self.players[k].AS[self.curTime], \
						self.players[k].actionValue(self.curTime,self.playType), self.players[k].curReward, \
						self.config.actionList[np.argmax(self.players[k].action)]]]

			else:
				self.players[k].hist2 += [[self.curTime,self.players[k].IL, self.players[k].OO, self.players[k].AO[self.curTime], self.players[k].AS[self.curTime], \
						self.players[k].actionValue(self.curTime,self.playType), self.players[k].curReward, 0]]

			# updates OO and AO at time t+1
			self.players[k].OO += self.players[k].actionValue(self.curTime, self.playType) # open order level update
			leadTime = randint(self.config.leadRecOrderLow[k], self.config.leadRecOrderUp[k])
			if self.players[k].agentNum < self.config.NoAgent-1:
				self.players[k+1].AO[self.curTime + leadTime] += self.players[k].actionValue(self.curTime, self.playType) # open order level update


	def playGame(self, demand, playType):
		self.resetGame(demand, playType)

		# run the game
		while self.curTime <= self.T:
			self.handelAction()
			self.next()


			for k in range(0,self.config.NoAgent):					
				if (self.players[k].compTypeTrain == "dnn" and playType == "train") or (self.players[k].compTypeTest == "dnn" and playType == "test"):
					# control the learner agent 

					self.players[k].brain.train(self.players[k].nextObservation,self.players[k].action, \
								self.players[k].curReward,self.curTime == self.T,self.playType)
		if self.config.ifUsedistTotReward and playType == "train":
			self.distTotReward()		
		return [-1*self.players[i].cumReward for i in range(0,self.config.NoAgent)]
	
	# check the Shang and Song (2003) condition, and if it works, obtains the base stock policy values for each agent
	def getOptimalSol(self):
		# if self.config.NoAgent !=1:
		if self.config.NoAgent !=1 and 1 == 2:
			# check the Shang and Song (2003) condition.
			for k in range(self.config.NoAgent-1):
				if not (self.players[k].c_h == self.players[k+1].c_h and self.players[k+1].c_p == 0):
					self.ifOptimalSolExist = False
				
			# if the Shang and Song (2003) condition satisfied, it runs the algorithm
			if self.ifOptimalSolExist == True:
				calculations = np.zeros((7,self.config.NoAgent))
				for k in range(self.config.NoAgent):
					# DL_high
					calculations[0][k] = ((self.config.leadRecItemLow +self.config.leadRecItemUp + 2)/2 \
									  + (self.config.leadRecOrderLow+self.config.leadRecOrderUp + 2)/2)* \
										(self.config.demandUp - self.config.demandLow- 1)
					if k > 0:
						calculations[0][k] += calculations[0][k-1]
					# probability_high
					nominator_ch = 0
					low_denominator_ch = 0				
					for j in range(k,self.config.NoAgent):
						if j < self.config.NoAgent-1:
							nominator_ch += self.players[j+1].c_h
						low_denominator_ch += self.players[j].c_h 
					if k == 0:
						high_denominator_ch = low_denominator_ch
					calculations[2][k] = (self.players[0].c_p + nominator_ch)/(self.players[0].c_p + low_denominator_ch + 0.0)
					# probability_low
					calculations[3][k] = (self.players[0].c_p + nominator_ch)/(self.players[0].c_p + high_denominator_ch + 0.0)
				# S_high
				calculations[4] = np.round(np.multiply(calculations[0],calculations[2]))
				# S_low
				calculations[5] = np.round(np.multiply(calculations[0],calculations[3]))
				# S_avg
				calculations[6] = np.round(np.mean(calculations[4:6], axis=0))
				# S', set the base stock values into each agent.
				for k in range(self.config.NoAgent):
					if k == 0:
						self.players[k].optmlBaseStock = calculations[6][k]
						
					else:
						self.players[k].optmlBaseStock = calculations[6][k] - calculations[6][k-1]
						if self.players[k].optmlBaseStock < 0:
							self.players[k].optmlBaseStock = 0
		elif self.config.NoAgent ==1:				
			if self.config.demandDistribution==0:
				self.players[0].optmlBaseStock = np.ceil(self.config.c_h[0]/(self.config.c_h[0]+self.config.c_p[0]+ 0.0))*((self.config.demandUp-self.config.demandLow-1)/2)*self.config.leadRecItemUp
		elif 1 == 1:
			f = self.config.f
			f_init = self.config.f_init
			for k in range(self.config.NoAgent):
				self.players[k].optmlBaseStock = f[k]
				self.players[k].init_optmlBaseStock = f_init[k]
				
	def doTestMid(self, demandTs):
		if self.config.ifPlaySavedData:
			for c,i in enumerate(self.config.agentTypes):
				if i == "dnn":
					dnn_agent = c
					break

		self.resultTest = []
		for i in range(self.config.testRepeatMid):
			if self.config.ifPlaySavedData:
				hist2 = np.load(os.path.join(self.config.model_dir,'DQN-0-player-'+str(dnn_agent)+'-'+str(i)+'.npy'))
				self.loaded_dqn_actions = hist2[:,7]
			self.doTest(i,demandTs[i])
		
		print("---------------------------------------------------------------------------------------")
		resultSummary = np.array(self.resultTest).mean(axis=0).tolist()	
		
		
		if self.ifOptimalSolExist:
			print('SUMMARY; {0:s}; ITER= {1:d}; DNN= {2:s}; SUM = {3:2.4f}; RND= {4:s}; SUM = {5:2.4f}; STRM= {6:s}; SUM = {7:2.4f}; BS= {8:s}; SUM = {9:2.4f}'.format(strftime("%Y-%m-%d %H:%M:%S", gmtime()) , 
				self.curGame, [round(resultSummary[0][i],2) for i in range(0,self.config.NoAgent)], sum(resultSummary[0]), 
				[round(resultSummary[1][i],2) for i in range(0,self.config.NoAgent)], sum(resultSummary[1]),
				[round(resultSummary[2][i],2) for i in range(0,self.config.NoAgent)], sum(resultSummary[2]), 
				[round(resultSummary[3][i],2) for i in range(0,self.config.NoAgent)], sum(resultSummary[3])))	

		else:
			print('SUMMARY; {0:s}; ITER= {1:d}; DNN= {2:s}; SUM = {3:2.4f}; RND= {4:s}; SUM = {5:2.4f}; STRM= {6:s}; SUM = {7:2.4f}'.format(strftime("%Y-%m-%d %H:%M:%S", gmtime()) , 
				self.curGame, [round(resultSummary[0][i],2) for i in range(0,self.config.NoAgent)], sum(resultSummary[0]), 
				[round(resultSummary[1][i],2) for i in range(0,self.config.NoAgent)], sum(resultSummary[1]),
				[round(resultSummary[2][i],2) for i in range(0,self.config.NoAgent)], sum(resultSummary[2])))
		
		print("=======================================================================================")


						

	def doTest(self, m,demand):
		import matplotlib.pyplot as plt
		
		if (self.config.ifSaveFigure) and (self.curGame in range(self.config.saveFigInt[0],self.config.saveFigInt[1])):
			plt.figure(self.curGame, figsize=(12, 8), dpi=80, facecolor='w', edgecolor='k')
		
		self.demand = demand
		# use dnn to get output.
		Rsltdnn,plt = self.tester(self.config.agentTypes ,plt, 'b', 'DQN' ,m)
		baseStockdata = self.players[0].dnnBaseStock

		# check some condition to avoid doing same test middle again.
		if ((self.config.ifSaveFigure) and (self.curGame in range(self.config.saveFigInt[0],self.config.saveFigInt[1]))) \
			or (self.curGame >= self.config.maxEpisodesTrain-1) or (len(self.middleTestResult) < self.config.testRepeatMid):

			# use random to get output.
			RsltRnd ,plt= self.tester(["rnd","rnd","rnd","rnd"], plt,'y21', 'RAND' ,m)
							
			# use formual to get output.
			RsltFrmu ,plt= self.tester(["frmu","frmu","frmu","frmu"],plt, 'g', 'Strm' ,m)

			# use optimal strategy to get output, if it works.
			if self.ifOptimalSolExist:
				if self.config.agentTypes == ["dnn", "frmu","frmu","frmu"]:
					RsltOptm ,plt= self.tester(["optm","frmu","frmu","frmu"],plt, 'r', 'Strm-BS' ,m)
				elif self.config.agentTypes == ["frmu", "dnn","frmu","frmu"]:
					 RsltOptm ,plt= self.tester(["frmu","optm","frmu","frmu"],plt, 'r', 'Strm-BS' ,m)
				elif self.config.agentTypes == ["frmu", "frmu","dnn","frmu"]:
					 RsltOptm ,plt= self.tester(["frmu","frmu","optm","frmu"],plt, 'r', 'Strm-BS' ,m)
				elif self.config.agentTypes == ["frmu", "frmu","frmu","dnn"]:				 
					 RsltOptm ,plt= self.tester(["frmu","frmu","frmu","optm"],plt, 'r', 'Strm-BS' ,m)
				elif self.config.agentTypes == ["dnn", "rnd","rnd","rnd"]:
					RsltOptm ,plt= self.tester(["optm","rnd","rnd","rnd"],plt, 'r', 'RND-BS' ,m)
				elif self.config.agentTypes == ["rnd", "dnn","rnd","rnd"]:
					 RsltOptm ,plt= self.tester(["rnd","optm","rnd","rnd"],plt, 'r', 'RND-BS' ,m)
				elif self.config.agentTypes == ["rnd", "rnd","dnn","rnd"]:
					 RsltOptm ,plt= self.tester(["rnd","rnd","optm","rnd"],plt, 'r', 'RND-BS' ,m)
				elif self.config.agentTypes == ["rnd", "rnd","rnd","dnn"]:				 
					 RsltOptm ,plt= self.tester(["rnd","rnd","rnd","optm"],plt, 'r', 'RND-BS' ,m)
				else:
					RsltOptm ,plt= self.tester(["optm","optm","optm","optm"],plt, 'r', 'BS' ,m)			
			# hold the results of the optimal solution
				self.middleTestResult += [[RsltRnd,RsltFrmu,RsltOptm]]
			else:
				self.middleTestResult += [[RsltRnd,RsltFrmu]]
			
		else:
			# return the obtained results into their lists
			RsltRnd = self.middleTestResult[m][0]
			RsltFrmu = self.middleTestResult[m][1]
			if self.ifOptimalSolExist:
				RsltOptm = self.middleTestResult[m][2]
			
		# save the figure
		if self.config.ifSaveFigure and (self.curGame in range(self.config.saveFigInt[0],self.config.saveFigInt[1])):
			savePlot(self.players, self.curGame, Rsltdnn  ,RsltFrmu, RsltOptm , self.config, m)
				
		if self.ifOptimalSolExist:
			print('output; {0:s}; Iter= {1:s}; dnn= {2:s}; sum = {3:2.4f}; rnd= {4:s}; sum = {5:2.4f}; frmu= {6:s}; sum = {7:2.4f}; BS= {8:s}; sum = {9:2.4f}'.format(
			strftime("%Y-%m-%d %H:%M:%S", gmtime()) , str(str(self.curGame)+"-"+str(m)), [round(Rsltdnn[i],2) for i in range(0,self.config.NoAgent)], sum(Rsltdnn), 
			[round(RsltRnd[i],2) for i in range(0,self.config.NoAgent)], sum(RsltRnd),
			[round(RsltFrmu[i],2) for i in range(0,self.config.NoAgent)], sum(RsltFrmu), 
			[round(RsltOptm[i],2) for i in range(0,self.config.NoAgent)], sum(RsltOptm)))	
			self.resultTest +=  [[Rsltdnn,RsltRnd,RsltFrmu,RsltOptm]]

		else:
			print('output; {0:s}; Iter= {1:s}; dnn= {2:s}; sum = {3:2.4f}; rnd= {4:s}; sum = {5:2.4f}; frmu= {6:s}; sum = {7:2.4f}'.format(strftime("%Y-%m-%d %H:%M:%S", gmtime()) , 
			str(str(self.curGame)+"-"+str(m)), [round(Rsltdnn[i],2) for i in range(0,self.config.NoAgent)], sum(Rsltdnn), 
			[round(RsltRnd[i],2) for i in range(0,self.config.NoAgent)], sum(RsltRnd),
			[round(RsltFrmu[i],2) for i in range(0,self.config.NoAgent)], sum(RsltFrmu)))	
			
			self.resultTest += [[Rsltdnn,RsltRnd,RsltFrmu]]

		return sum(Rsltdnn)
		
	def tester(self,testType,plt, colori, labeli ,m):
		
		# set computation type for test
		for k in range(0,self.config.NoAgent):
			self.players[k].compTypeTest = testType[k]
		# run the episode to get the results.
		result = self.playGame(self.demand,"test")
		# add the results into the figure
		if self.config.ifSaveFigure and (self.curGame in range(self.config.saveFigInt[0],self.config.saveFigInt[1])) and (testType[0] != "rnd"):
			plt = plotting(plt,[np.array(self.players[i].hist) for i in range(0,self.config.NoAgent)],colori, labeli)			
		if self.config.ifsaveHistInterval and ((self.curGame == 0) or (self.curGame == 1) or (self.curGame == 2) or(self.curGame == 3) or ((self.curGame - 1) % self.config.saveHistInterval == 0)\
			or ((self.curGame) % self.config.saveHistInterval == 0) or ((self.curGame) % self.config.saveHistInterval == 1) \
			or ((self.curGame) % self.config.saveHistInterval == 2)) :
			for k in range(0,self.config.NoAgent): 
				name = labeli + "-" + str(self.curGame) + "-" + "player" + "-" + str(k)+ "-" + str(m)
				np.save(os.path.join(self.config.model_dir,name), np.array(self.players[k].hist2))
	
		# save the figure of base stocks
		# if self.config.ifSaveFigure and (self.curGame in range(self.config.saveFigInt[0],self.config.saveFigInt[1])):
		# 	for k in range(self.config.NoAgent):
		# 		if self.players[k].compTypeTest == 'dnn':
		# 			plotBaseStock(self.players[k].dnnBaseStock, 'b', 'base stock of agent '+ str(self.players[k].agentNum), self.curGame, self.config, m)

		return result,plt
		

	def update_OO(self):
		for k in range(0,self.config.NoAgent):
			if k < self.config.NoAgent - 1:
				self.players[k].OO = sum(self.players[k+1].AO) + sum(self.players[k].AS)
			else:
				self.players[k].OO = sum(self.players[k].AS)

