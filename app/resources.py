import random
import asyncio as aio
from uuid import uuid1 as UU1, uuid4 as UU4
from datetime import datetime as dtm
from time import perf_counter as tpc

from yaml import safe_load
from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine as dbeng
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from cryptography.fernet import Fernet, MultiFernet as MFT
# from flask_jwt_extended import jwt_required, get_jwt_identity

from model import cfg
from model import Keys as K
from model import ErrorLogs as ERL
from model import KeyRequester as KR

urx = 'postgresql://' +cfg['datastore']['uid']+ ':' +cfg['datastore']['pwd']+ '@' +cfg['datastore']['host']+ ':' +str(cfg['datastore']['port'])+ '/' +cfg['datastore']['db']

now = tpc()
pub_key_store = []
pvt_key_store = []
app_key = 'rH_wkQVjM3ub6LOD1qGNA8fff12cIvljEDwWtKj-VNw='


def dataSession(urx):
    pgx = dbeng(urx)
    SessionClass = sessionmaker(bind=pgx)
    Session = SessionClass()
    return Session


def record_error(
    urx,
    e_class,
    e_rsrc,
    e_msg
):
    try:
        err_ssn = dataSession(urx)
        mydoc = {
            'err_class': e_class,
            'err_resource': e_rsrc,
            'err_msg': e_msg,
            'app_stamp': dtm.utcnow(),
            'tbl_id': UU1(),
        }
        err_ssn.add(ERL(**mydoc))
        err_ssn.commit()
        err_ssn.close()
    except Exception as err:
        print('Unable to Write to Error Logs...')
        print(err)
    return None


def record_key_request(key_id, requester):
    event_session = dataSession(urx)
    event_doc = {
        'key_id': key_id,
        'requester': requester,
        'request_stamp': dtm.utcnow(),
        'tbl_id': UU4()
    }
    event_session.add(KR(**event_doc))
    event_session.commit()
    return None


try:
    KAFKA = cfg['kafka']['enable']
    master_key = cfg['key']['master_key']
    global_key = cfg['key']['global_key']
    key_size = int(cfg['key']['key_size'])
except Exception as err:
    record_error(
        urx,
        e_class='resources',
        e_rsrc='import-app-config',
        e_msg=str(err)
    )

try:
    event_session = dataSession(urx)
    pub_key_store_en = event_session.query(K).filter(K.active==True).with_entities(K.key_id, K.pub_key).all()
    event_session.close()
    event_session = dataSession(urx)
    pvt_key_store_en = event_session.query(K).filter(K.deprecated==False).with_entities(K.key_id, K.pvt_key).all()
    event_session = dataSession(urx)
except Exception as err:
    record_error(
        urx,
        e_class='resource',
        e_rsrc='fetch-datastore-keys',
        e_msg=str(err)
    )

try:
    unlock_set = [Fernet(app_key.encode()), Fernet(global_key.encode())]
    mft = MFT(unlock_set)
except Exception as err:
    record_error(
        urx,
        e_class='heart',
        e_rsrc='Build MFT Object',
        e_msg=str(err)
    )

try:
    for _ in pvt_key_store_en:
        _tup_ = {'key_id': _[0]}
        _pvt_ = serialization.load_pem_private_key(
                _[1],
                password=mft.decrypt(master_key.encode()),
                backend=default_backend()
        )
        _pem_ = _pvt_.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode()
        _tup_['pvt_key'] = _pem_
        pvt_key_store.append(_tup_)
    pvt_key_store_en.clear()
except Exception as err:
    record_error(
        urx,
        e_class='heart',
        e_rsrc='Decrypt Private Store',
        e_msg=str(err)
    )

try:
    for _ in pub_key_store_en:
        _tup_ = {
            'key_id': _[0],
            'pub_key': _[1].decode(),
        }
        pub_key_store.append(_tup_)
except Exception as err:
    record_error(
        urx,
        e_class='heart',
        e_rsrc='Decode Public Store',
        e_msg=str(err)
    )

if KAFKA:
    P = Producer({'bootstrap.servers': cfg['kafka']['host']})

pub_key_point = '/krs/v1/pub_key'
pvt_key_point = '/krs/v1/pvt_key'
app = FastAPI()


class KeyDoc(BaseModel):
    key_id: str
    pvt_key: int = 8


async def key_private(kid):
    kounter = 0
    for keypair in pvt_key_store:
        kounter += 1
        if keypair['key_id'] == kid:
            print(kounter)
            return keypair
    return {kid: 'Private Key not Found'}


@app.get(pvt_key_point)
async def get_pvt(key_doc: KeyDoc):
    kid = key_doc.key_id
    print('kid :' + kid)

    try:
        done, pending = await aio.wait([key_private(kid)])
    except Exception as err:
        print(err)

    if done:
        for task in done:
            return task.result()
    return None


@app.get(pub_key_point)
async def get_pub():
    return random.choice(pub_key_store)


@app.get("/")
async def root():
    return {"message": "AIO"}