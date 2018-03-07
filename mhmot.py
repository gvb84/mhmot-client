#!/usr/bin/env python3
#
# "THE BEER-WARE LICENSE" (Revision 42): gvb@santarago.org wote this file.  As
# long as you retain this notice you can do whatever you want with this stuff.
# If we meet some day, and you think this stuff is worth it, you can buy me a
# beer in return. Vincent Berg

"""
This is a very simple Python client that was a quick and dirty implementation
after I reverse engineered the Met Het Mes Op Tafel mobile application. It
talks to the backend and has the ability to play games and answer questions.
It does so randomly by squaring off two bot users against eachother whilst
saving the answers to questions after each round in a database. This could be
used to create a perfect playing bot that will either win every game or at
least always tie (if it can't outbluff the opposing player and that player has
every question correct too).

This code was only used to square off a few bots against eachother and to
attain a weekly highscore once. It was not used to play games against actual
human users as to not ruin their fun. Besides that the database of questions
will not be published for the same reason. Of course any player can start
jotting down the answers to questions and this can be done with pen and paper
too and there's nothing really that can be done against it. 

Only rate-limiting can really help against running bots that play very quickly
against eachother but if someone plays continuously and slowly within the normal
parameters one can still always build up the database and slowly build up
a perfect playing bot.

This code is hella dirty and the database code morphed into what it is below
but I'm way too lazy to fix it up and rewrite it up to my usual standards. It
got the job done for what I needed this code for and this is now published
for anyone who might like to try or mess with this too.

Released under the terms of the beer-ware license!

This was a fun exercise. No harm intended.

-- Vincent / @santaragolabs
"""

import requests, json, base64, random, string, time

headers = {
	"X-MhMoT-PlatformName": "Android",
	"X-MhMoT-PlatformVersion": "24",
	"X-MhMoT-ApiVersion": "1.0",
	"X-MhMoT-ApplicationVersion": "1.1.0"
}

base_url = "https://mhmot.elastique.nl/api"

DATABASE = "questions.db"
global database
global match
global tries
match = 0
tries = 0

class Client():
	def __init__(self, username=None, password=None, token=None):
		if not username and password or username and not password:
			raise Exception("username and password should go together")
		elif username is not None and password is not None:
			if not self.login(username, password):
				raise Exception("couldn't login")
		elif token is None:
			raise Exception("no token or username/password specified")
		elif token:
			self.token = token

		# only set if we manage to extract it properly from the token
		self.user_id = None

		# try and workaroudn the padding errors
		for i in range(0, 5):
			try:
				bdata = base64.b64decode(self.token.split(".")[1][:-i])
				bdata = "%s}" % bdata.decode("ascii")
				data = json.loads(bdata)
				self.user_id = int(data["id"])
				break
			except:
				pass

		self.headers = {}
		for h in headers:
			self.headers[h] = headers[h]
		self.headers["Authorization"] = "Bearer %s" % self.token
		
	def login(self, username, password):
		ret = requests.post("%s/users/login" % (base_url), headers=headers, data={"email":username,"password":password})
		data = json.loads(ret.text)
		if "data" in data:
			data = data["data"]
			self.id = data["id"]
			res_headers = ret.headers
			token = res_headers["token"]
			self.token = token
			return True
		return False

	def get(self, req):
		ret = requests.get("%s/%s" % (base_url, req), headers=self.headers)
		return ret.text

	def post(self, req, **rest):
		ret = requests.post("%s/%s" % (base_url, req), headers=self.headers, **rest)
		return ret.text

	def put(self, req, **rest):
		ret = requests.put("%s/%s" % (base_url, req), headers=self.headers, **rest)
		return (ret.text, ret.status_code)

	def getAllGames(self):
		# get an overview of all games
		data = self.get("games/overview")
		games = json.loads(data)["data"]
		active, pending, ended = games["active"], games["pending"], games["ended"]
		active = [Game(a, self) for a in active]
		pending = [Game(p, self) for p in pending]
		ended = [Game(e, self) for e in ended]
		return (active, pending, ended)

	def getOverview2(self, i):
		data = self.get("games/%i/overview2" % i)
		print(data)
		return json.loads(data)["data"]

	def inviteUser(self, user_id):
		data = self.post("games", data={"user_id":user_id})
		data = json.loads(data)
		if "error" in data:
			return False
		return Game(data["data"], self)

	def authChannel(self, channel_name, **rest):
		from websocket import create_connection
		ws = create_connection("wss://ws-eu.pusher.com/app/4d0b083b1f1da7872191?client=java-client&protocol=5&version=1.4.0")
		result = ws.recv()
		resdata = json.loads(result)
		sdata = json.loads(resdata["data"])
		socket_id = sdata["socket_id"]

		data = {"channel_name":channel_name, "socketid":socket_id}
		xbase_url = base_url[:-4]
		ret = requests.post("%s/pusher/auth" % (xbase_url,), headers=self.headers, data=data, **rest)
		channel_data = ret.text
		self.channel_data = json.loads(channel_data)	

		wsdata = {"event":"pusher:subscribe", "data":self.channel_data}
		wsdata["data"]["channel"]=channel_name

		ws.send(json.dumps(wsdata))
		#ws.send("Hello, World")
		result = ws.recv()
		#ws.close()
		
		return self.channel_data

class Question():
	def __init__(self, data):
		self.id = data["id"]
		self.title = data["title"]
		self.correct = False if "isCorrect" not in data or not data["isCorrect"] else True
		self.answer = False if "correct" not in data else data["correct"]
		self.category = data["category"]
	
	def __repr__(self):
		return "Question(%i) <%s> - %s" % (self.id, self.title, self.category)

class Event():
	def __init__(self, data):
		self.id = data["id"]
		self.name = data["eventName"]
		self.data = data["data"]

	def __repr__(self):
		return "Event(%i) <%s>" % (self.id, self.name)

class Game():
	def __init__(self, data, client=None):
		self.players = [(p["nickname"], int(p["id"])) for p in data["players"]]	
		self.id = int(data["id"])
		self.channelName = data["channelName"]
		self.client = client

	def __repr__(self):
		return "Game(%i) <%s vs %s>" % (self.id, self.players[0], self.players[1])

	def getEvents(self):
		data = self.client.get("games/%i/events" % self.id)
		events = json.loads(data)["data"]
		events = [Event(e) for e in events]
		return events

	def getOverview(self):
		data = self.client.get("games/%i/overview" % self.id)
		overview = json.loads(data)["data"]
		questions = [Question(x) for x in overview]
		return questions

	def getCorrect(self):
		data = self.client.get("games/%i/correct" % self.id)
		overview = json.loads(data)["data"]
		questions = [Question(x) for x in overview]
		return questions
	
	def deleteGame(self):
		data = self.client.put("games/%i/delete" % self.id)
		return data

	def getQuestions(self):
		data = self.client.get("games/%i/questions" % self.id)
		overview = json.loads(data)["data"]
		questions = [Question(x) for x in overview]
		return questions

	def acceptInvite(self):
		data, code = self.client.put("games/%i/invite/accept" % self.id)
		if code == 200:
			return True
		return False

	def endRound(self):
		data = self.client.post("games/%i/endround" % self.id)
		return data	

	def sendPass(self):
		data = self.client.post("games/%i/pass" % self.id)
		return data
		
	# ansers are a dict of question id -> answer string
	def answerQuestions(self, answers={}):
		data = {"answers":[]}
		for a in answers:
			data["answers"].append({"question":a,"answer":answers[a]})
		data = self.client.post("games/%i/answers" % self.id, json=data)
		
		x=json.loads(data)
		if x["statusCode"] == 200:
			return True
		return False	
	


""" 
change the tokens here or use a login user by specifying the
username and password combination when creating the Client; see the
Client class implementation above for details
"""

token_1 = "CENSORED"
token_2 = "CENSORED"

c1 = Client(token=token_1)
c2 = Client(token=token_2)

def get_r(n):
	return "".join([random.choice(string.ascii_lowercase) for i in range(n)])

def delete_game_maybe(game, c1, c2):
	player_ids = [p[1] for p in game.players]
	if c1.user_id in player_ids and c2.user_id in player_ids:
		print("deleting game %i" % game.id)
		game.deleteGame()

def delete_game(c1, c2):
	active, pending, ended = c1.getAllGames()
	for a in active:
		delete_game_maybe(a, c1, c2)
	for a in pending:
		delete_game_maybe(a, c1, c2)

def load_database():
	global database
	try:
		database = json.loads(open(DATABASE, "r").read())
	except:
		database = {}

def get_question_from_db(q):
	global database
	try:
		ret = database[int(q.id)]
		print("already found %i -> %s" % (q.id, q.title))
	except:
		ret = None
	print("returning %s from get_q_from_db" % (ret))
	return ret

def save_question_to_db(q):
	global database
	try:
		obj = database[int(q.id)]
		print("already in database for id %i with %s -> %s" % (q.id, database[q.id][0], q.title))
	except:
		database[int(q.id)] = (q.title, q.answer, q.category)

def save_database():
	global database
	open(DATABASE, "w+").write(json.dumps(database))
	
def play_round(g1, g2, final=False):
	print("playing round")
	q1 = g1.getQuestions()
	q2 = g2.getQuestions()

	# generate random nonsensical answers
	answers1, answers2 = {}, {}
	for q in q1:
		answers1[q.id] = get_r(8)
		answers2[q.id] = get_r(8)

	# now look for all questions if we have it in database already
	# and set them
	tosave = []
	for q in q1:
		qdb = get_question_from_db(q)
		print(qdb)
		if not qdb:
			global tries
			tries = tries + 1
			tosave.append(q.id)
			continue
		else:
			global match
			match = match + 1
			if qdb[0] != q.title:
				print("sanity check; question was %s, and is now %s for id: %i" % (qdb[0], q.title, q.id))
			else:
				print("not using random answer but correct for id %i and %s" % (q.id, q.title))
			answers1[q.id] = (qdb[1])
			answers2[q.id] = (qdb[1])

	
	g1.answerQuestions(answers1)
	g2.answerQuestions(answers2)

	q1 = g1.getCorrect()
	for q in q1:
		if q.id in tosave:
			save_question_to_db(q)
		else:
			print("not saving with %i %s" % (q.id, q.title))

	if not final:
		g1.sendPass()
		g2.sendPass()

	g1.endRound()
	g2.endRound()
	print("-----")

def play_game(c1, c2):
	g1 = c1.inviteUser(c2.user_id)
	if not g1:
		print("invite not succeeded")
		return

	found = False
	active, pending, ended = c2.getAllGames()
	for g2 in pending:
		if g2.id == g1.id:
			# found right pending game
			found = True
			break
	if not found:
		print("couldn't find invite")

	# c2 needs to accept the invite
	g2.acceptInvite()

	# setup the websocket channels which will
	# officially start the game
	c1.authChannel(g1.channelName)
	c2.authChannel(g2.channelName)

	time.sleep(1)

	for i in range(0, 4):
		play_round(g1, g2)
	play_round(g1, g2, True)

load_database()

try:
	delete_game(c1, c2)

	# play two games with a 15sec timeout in between
	play_game(c1, c2)
	time.sleep(15)
	play_game(c1, c2)

	save_database()

except Exception as e:
	print(e)
	pass

print("total questions in db: %i" % len(database))
print("total answers found in db: %i" % match)
print("new questions added to db: %i" % tries)

save_database()
