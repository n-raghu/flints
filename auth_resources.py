import sys
from uuid import uuid4 as UU4
from datetime import timedelta as tdt, datetime as dtm

from flask_restful import Resource
from confluent_kafka import Producer
from sqlalchemy.orm import sessionmaker
from flask_jwt_extended import create_access_token
from flask import jsonify, abort, request, make_response
from sqlalchemy import create_engine as dbeng, text as alchemyText

from auth_model import User as U, UserRole as UR, cfg

LIFE_TIME_TOKEN = 3116969069
KAFKA = cfg['kafka']['enable']
urx = 'postgresql://' +cfg['datastore']['uid']+ ':' +cfg['datastore']['pwd']+ '@' +cfg['datastore']['host']+ ':' +str(cfg['datastore']['port'])+ '/' +cfg['datastore']['db']

if KAFKA:
	P = Producer({'bootstrap.servers': cfg['kafka']['host']})

def dataSession(urx):
	pgx = dbeng(urx)
	SessionClass = sessionmaker(bind=pgx)
	Session = SessionClass()
	return Session

class GenNewToken(Resource):
	
	def post(self):
		if not request.get_json():
			abort(400)
		obo = request.get_json()
		access_token = 'Unauthorized User...'
		uname = request.json.get('uid', None)
		paswd = request.json.get('pwd', None)
		eventSession = dataSession(urx)
		userdoc = eventSession.query(U).filter(U.uid==uname).first()
		eventSession.close()
		if paswd == userdoc.__dict__['pwd']:
			eventSession=dataSession(urx)
			roledoc = eventSession.query(UR).filter(UR.rid==userdoc.__dict__['roleid']).first()
			eventSession.close()
			tokenTime = roledoc.__dict__['tokentime']
			if tokenTime == -1:
				access_token = create_access_token(identity=uname,expires_delta=tdt(seconds=LIFE_TIME_TOKEN))
			else:
				access_token = create_access_token(identity=uname,expires_delta=tdt(seconds=tokenTime))
			eventDoc = {'event':'access-tokens','action':'gen-access-token','etime':dtm.utcnow(),'event_owner':uname,'eventid':UU4().hex}
			if KAFKA:
				P.poll(0)
				P.produce('topic-events',packb(eventDoc,default=encode_dtm,use_bin_type=True),callback=delivery_report)
		else:
			access_token = 'Password did not match'
		return jsonify(
			{
				'access_token':access_token,
				'token_owner': uname
			}
		)
