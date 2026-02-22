import asyncio
import copy
import importlib
import json
import logging
import sys
import time
from collections import namedtuple
from collections.abc import Callable
from datetime import datetime
from io import StringIO

# 운영 체제 확인
module_name = "Crypto" if sys.platform != "win32" else "crypto"
alias_module_name = "crypto" if sys.platform != "win32" else "Crypto"
# 패키지 동적 import
crypto_module = importlib.import_module(module_name)
# alias_module_name 로 crypto_module 등록
sys.modules[alias_module_name] = crypto_module

import pandas as pd
# pip install requests (패키지설치)
import requests
# 웹 소켓 모듈을 선언한다.
import websockets

# pip install crypto
# pip install pycryptodome
from crypto.Cipher import AES
from crypto.Util.Padding import unpad

from base64 import b64decode

from django.conf import settings  # 유저 모델 참조용
from django.utils import timezone

from investments.models import Account, Token


class KisAuth:
    def __init__(self, account: Account):
        self.account = account

        self._TRENV = tuple()
        self._autoReAuth = False  # url_fetch 시 자동 재인증 여부
        self._DEBUG = False
        self._isPaper = False  # 모의투자여부
        self._smartSleep = 0.05  # 실전투자 0.05, 모의투자 0.5

        # 기본 헤더값 정의
        self._base_headers = {
            "Content-Type": "application/json",
            "Accept": "text/plain",
            "charset": "UTF-8",
            "User-Agent": settings.USER_AGENT,
        }

    # 토큰 발급 받아 저장 (토큰값, 토큰 유효시간,1일, 6시간 이내 발급신청시는 기존 토큰값과 동일, 발급시 알림톡 발송)
    def save_token(self, my_token, my_expired):
        naive_expired = datetime.strptime(my_expired, "%Y-%m-%d %H:%M:%S")
        aware_expired = timezone.make_aware(naive_expired)

        Token.objects.update_or_create(
            account=self.account,  # 조회 조건 (어떤 계좌의 토큰을 찾을 것인가)
            defaults={  # 업데이트할 내용 (찾았으면 수정, 없으면 생성 시 사용할 값)
                "access_token": my_token,
                "issued_at": timezone.now(),
                "expired_at": aware_expired,
            },
        )
        self.account.refresh_from_db()  # 토큰 생성 후 DB에서 다시 동기화

    # 토큰 확인 (토큰값, 토큰 유효시간_1일, 6시간 이내 발급신청시는 기존 토큰값과 동일, 발급시 알림톡 발송)
    def read_token(self):
        # self.account 객체에 'token'이라는 속성(데이터)이 실제로 있는지 확인
        if hasattr(self.account, 'token'):
            token = self.account.token
            # 만료 여부 체크 (is_expired_custom 로직 사용)
            if not token.is_expired_custom:
                return token.access_token

        return None

    # 토큰 유효시간 체크해서 만료된 토큰이면 재발급처리
    def _getBaseHeader(self):
        if self._autoReAuth:
            self.reAuth()
        return copy.deepcopy(self._base_headers)

    # 가져오기 : 앱키, 앱시크리트, 종합계좌번호(계좌번호 중 숫자8자리), 계좌상품코드(계좌번호 중 숫자2자리), 토큰, 도메인
    def _setTRENV(self, cfg):
        nt1 = namedtuple(
            "KISEnv",
            ["my_app", "my_sec", "my_acct", "my_prod", "my_htsid", "my_token", "my_url", "my_url_ws"],
        )

        d = {
            "my_app": cfg["my_app"],  # 앱키
            "my_sec": cfg["my_sec"],  # 앱시크리트
            "my_acct": cfg["my_acct"],  # 종합계좌번호(8자리)
            "my_prod": cfg["my_prod"],  # 계좌상품코드(2자리)
            "my_htsid": cfg["my_htsid"],  # HTS ID
            "my_token": cfg["my_token"],  # 토큰
            "my_url": cfg[
                "my_url"
            ],  # 실전 도메인 (https://openapi.koreainvestment.com:9443)
            "my_url_ws": cfg["my_url_ws"],
        }  # 모의 도메인 (https://openapivts.koreainvestment.com:29443)

        self._TRENV = nt1(**d)

    def isPaperTrading(self):  # 모의투자 매매 여부
        return self._isPaper

    def changeTREnv(self, token_key):
        cfg = dict()
        cfg["my_app"] = self.account.app_key
        cfg["my_sec"] = self.account.secret_key
        cfg["my_acct"] = self.account.account_number[8:]
        cfg["my_prod"] = self.account.account_number[-2:]
        cfg["my_htsid"] = self.account.hts_id
        cfg["my_url"] = settings.KIS_URL
        cfg["my_url_ws"] = settings.KIS_WS_URL

        try:
            my_token = self._TRENV.my_token
        except AttributeError:
            my_token = ""
        cfg["my_token"] = my_token if token_key else token_key

        self._setTRENV(cfg)

    def _getResultObject(self, json_data):
        _tc_ = namedtuple("res", json_data.keys())
        return _tc_(**json_data)

    # Token 발급, 유효기간 1일, 6시간 이내 발급시 기존 token값 유지, 발급시 알림톡 무조건 발송
    # 모의투자인 경우  svr='vps', 투자계좌(01)이 아닌경우 product='XX' 변경하세요 (계좌번호 뒤 2자리)
    def auth(self):
        p = {
            "grant_type": "client_credentials",
            "appkey": self.account.app_key,
            "appsecret": self.account.secret_key,
        }

        # 기존 발급된 토큰이 있는지 확인
        saved_token = self.read_token()  # 기존 발급 토큰 확인

        if saved_token is None:
            url = f"{settings.KIS_URL}/oauth2/tokenP"
            res = requests.post(url, data=json.dumps(p), headers=self._getBaseHeader())
            if res.status_code == 200:  # 토큰 정상 발급
                res_obj = self._getResultObject(res.json())
                my_token = res_obj.access_token
                my_expired = res_obj.access_token_token_expired

                self.save_token(my_token, my_expired)  # 새로 발급 받은 토큰 저장
            else:
                print("Get Authentification token fail!\nYou have to restart your app!!!")
                return
        else:
            my_token = saved_token

        self.changeTREnv(my_token)
        self._base_headers["authorization"] = f"Bearer {my_token}"
        self._base_headers["appkey"] = self._TRENV.my_app
        self._base_headers["appsecret"] = self._TRENV.my_sec

    # end of initialize, 토큰 재발급, 토큰 발급시 유효시간 1일
    def reAuth(self):
        if not self.account.token.is_expired_custom:
            self.auth()

    def smart_sleep(self):
        if self._DEBUG:
            print(f"[RateLimit] Sleeping {self._smartSleep}s ")

        time.sleep(self._smartSleep)

    def getTREnv(self):
        return self._TRENV

    def set_order_hash_key(self, h, p):
        url = f"{self.getTREnv().my_url}/uapi/hashkey"  # hashkey 발급 API URL

        res = requests.post(url, data=json.dumps(p), headers=h)
        rescode = res.status_code
        if rescode == 200:
            h["hashkey"] = self._getResultObject(res.json()).HASH
        else:
            print("Error:", rescode)

    def _url_fetch(self, api_url, ptr_id, tr_cont, params, appendHeaders=None, postFlag=False, hashFlag=True):
        url = f"{self.getTREnv().my_url}{api_url}"

        headers = self._getBaseHeader()  # 기본 header 값 정리

        # 추가 Header 설정
        tr_id = ptr_id
        if ptr_id[0] in ("T", "J", "C"):  # 실전투자용 TR id 체크
            if self.isPaperTrading():  # 모의투자용 TR id 식별
                tr_id = "V" + ptr_id[1:]

        headers["tr_id"] = tr_id  # 트랜젝션 TR id
        headers["custtype"] = "P"  # 일반(개인고객,법인고객) "P", 제휴사 "B"
        headers["tr_cont"] = tr_cont  # 트랜젝션 TR id

        if appendHeaders is not None:
            if len(appendHeaders) > 0:
                for x in appendHeaders.keys():
                    headers[x] = appendHeaders.get(x)

        if self._DEBUG:
            print("< Sending Info >")
            print(f"URL: {url}, TR: {tr_id}")
            print(f"<header>\n{headers}")
            print(f"<body>\n{params}")

        if postFlag:
            # if (hashFlag): set_order_hash_key(headers, params)
            res = requests.post(url, headers=headers, data=json.dumps(params))
        else:
            res = requests.get(url, headers=headers, params=params)

        if res.status_code == 200:
            ar = APIResp(res)
            if self._DEBUG:
                ar.printAll()
            return ar
        else:
            print("Error Code : " + str(res.status_code) + " | " + res.text)
            return APIRespError(res.status_code, res.text)

        return None

    ########### New - websocket 대응


# API 호출 응답에 필요한 처리 공통 함수
class APIResp:
    def __init__(self, resp):
        self._rescode = resp.status_code
        self._resp = resp
        self._header = self._setHeader()
        self._body = self._setBody()
        self._err_code = self._body.msg_cd
        self._err_message = self._body.msg1

    def getResCode(self):
        return self._rescode

    def _setHeader(self):
        fld = dict()
        for x in self._resp.headers.keys():
            if x.islower():
                fld[x] = self._resp.headers.get(x)
        _th_ = namedtuple("header", fld.keys())

        return _th_(**fld)

    def _setBody(self):
        _tb_ = namedtuple("body", self._resp.json().keys())

        return _tb_(**self._resp.json())

    def getHeader(self):
        return self._header

    def getBody(self):
        return self._body

    def getResponse(self):
        return self._resp

    def isOK(self):
        try:
            if self.getBody().rt_cd == "0":
                return True
            else:
                return False
        except:
            return False

    def getErrorCode(self):
        return self._err_code

    def getErrorMessage(self):
        return self._err_message

    def printAll(self):
        print("<Header>")
        for x in self.getHeader()._fields:
            print(f"\t-{x}: {getattr(self.getHeader(), x)}")
        print("<Body>")
        for x in self.getBody()._fields:
            print(f"\t-{x}: {getattr(self.getBody(), x)}")

    def printError(self, url):
        print(
            "-------------------------------\nError in response: ",
            self.getResCode(),
            " url=",
            url,
        )
        print(
            "rt_cd : ",
            self.getBody().rt_cd,
            "/ msg_cd : ",
            self.getErrorCode(),
            "/ msg1 : ",
            self.getErrorMessage(),
        )
        print("-------------------------------")

    # end of class APIResp


class APIRespError(APIResp):
    def __init__(self, status_code, error_text):
        # 부모 생성자 호출하지 않고 직접 초기화
        self.status_code = status_code
        self.error_text = error_text
        self._error_code = str(status_code)
        self._error_message = error_text

    def isOK(self):
        return False

    def getErrorCode(self):
        return self._error_code

    def getErrorMessage(self):
        return self._error_message

    def getBody(self):
        # 빈 객체 리턴 (속성 접근 시 AttributeError 방지)
        class EmptyBody:
            def __getattr__(self, name):
                return None

        return EmptyBody()

    def getHeader(self):
        # 빈 객체 리턴
        class EmptyHeader:
            tr_cont = ""

            def __getattr__(self, name):
                return ""

        return EmptyHeader()

    def printAll(self):
        print(f"=== ERROR RESPONSE ===")
        print(f"Status Code: {self.status_code}")
        print(f"Error Message: {self.error_text}")
        print(f"======================")

    def printError(self, url=""):
        print(f"Error Code : {self.status_code} | {self.error_text}")
        if url:
            print(f"URL: {url}")


class KISWebSocket(KisAuth):
    # init
    def __init__(self, account: Account, max_retries: int = 3):
        super().__init__(account)
        self.api_url = "/tryitout"
        self.max_retries = max_retries
        self.retry_count: int = 0

        self.on_result: Callable[
            [websockets.ClientConnection, str, pd.DataFrame, dict], None
        ] = None
        self.result_all_data: bool = False

        self._last_auth_time = None

        ########### New - websocket 대응
        self._base_headers_ws = {
            "content-type": "utf-8",
        }
        self.open_map: dict = {}
        self.data_map: dict = {}

    def _getBaseHeader_ws(self):
        if self._autoReAuth:
            self.reAuth_ws()
        return copy.deepcopy(self._base_headers_ws)

    def auth_ws(self):
        p = {
            "grant_type": "client_credentials",
            "appkey": self.account.app_key,
            "appsecret": self.account.secret_key,
        }

        url = f"{settings.KIS_URL}/oauth2/Approval"
        res = requests.post(url, data=json.dumps(p), headers=self._getBaseHeader())  # 토큰 발급
        if res.status_code == 200:  # 토큰 정상 발급
            approval_key = self._getResultObject(res.json()).approval_key
        else:
            print("Get Approval token fail!\nYou have to restart your app!!!")
            return

        # 웹소켓은 approval_key 사용하기 때문에 token 제거
        self.changeTREnv(None)

        self._base_headers_ws["approval_key"] = approval_key

        self._last_auth_time = timezone.now()

        if self._DEBUG:
            print(f"[{self._last_auth_time}] => get AUTH Key completed!")

    def reAuth_ws(self):
        n2 = datetime.now()
        if (n2 - self._last_auth_time).seconds >= 86400:
            self.auth_ws()

    def data_fetch(self, tr_id, tr_type, params, appendHeaders=None) -> dict:
        headers = self._getBaseHeader_ws()  # 기본 header 값 정리

        headers["tr_type"] = tr_type
        headers["custtype"] = "P"

        if appendHeaders is not None:
            if len(appendHeaders) > 0:
                for x in appendHeaders.keys():
                    headers[x] = appendHeaders.get(x)

        if self._DEBUG:
            print("< Sending Info >")
            print(f"TR: {tr_id}")
            print(f"<header>\n{headers}")

        inp = {
            "tr_id": tr_id,
        }
        inp.update(params)

        return {"header": headers, "body": {"input": inp}}

    # iv, ekey, encrypt 는 각 기능 메소드 파일에 저장할 수 있도록 dict에서 return 하도록
    def system_resp(self, data):
        isPingPong = False
        isUnSub = False
        isOk = False
        tr_msg = None
        tr_key = None
        encrypt, iv, ekey = None, None, None

        rdic = json.loads(data)

        tr_id = rdic["header"]["tr_id"]
        if tr_id != "PINGPONG":
            tr_key = rdic["header"]["tr_key"]
            encrypt = rdic["header"]["encrypt"]
        if rdic.get("body", None) is not None:
            isOk = True if rdic["body"]["rt_cd"] == "0" else False
            tr_msg = rdic["body"]["msg1"]
            # 복호화를 위한 key 를 추출
            if "output" in rdic["body"]:
                iv = rdic["body"]["output"]["iv"]
                ekey = rdic["body"]["output"]["key"]
            isUnSub = True if tr_msg[:5] == "UNSUB" else False
        else:
            isPingPong = True if tr_id == "PINGPONG" else False

        nt2 = namedtuple(
            "SysMsg",
            [
                "isOk",
                "tr_id",
                "tr_key",
                "isUnSub",
                "isPingPong",
                "tr_msg",
                "iv",
                "ekey",
                "encrypt",
            ],
        )
        d = {
            "isOk": isOk,
            "tr_id": tr_id,
            "tr_key": tr_key,
            "tr_msg": tr_msg,
            "isUnSub": isUnSub,
            "isPingPong": isPingPong,
            "iv": iv,
            "ekey": ekey,
            "encrypt": encrypt,
        }

        return nt2(**d)

    def aes_cbc_base64_dec(self, key, iv, cipher_text):
        if key is None or iv is None:
            raise AttributeError("key and iv cannot be None")

        cipher = AES.new(key.encode("utf-8"), AES.MODE_CBC, iv.encode("utf-8"))
        return bytes.decode(unpad(cipher.decrypt(b64decode(cipher_text)), AES.block_size))

    def add_open_map(
            self,
            name: str,
            request: Callable[[str, str, ...], (dict, list[str])],
            data: str | list[str],
            kwargs: dict = None,
    ):
        if self.open_map.get(name, None) is None:
            self.open_map[name] = {
                "func": request,
                "items": [],
                "kwargs": kwargs,
            }

        if type(data) is list:
            self.aopen_map[name]["items"] += data
        elif type(data) is str:
            self.open_map[name]["items"].append(data)

    def add_data_map(
            self,
            tr_id: str,
            columns: list = None,
            encrypt: str = None,
            key: str = None,
            iv: str = None,
    ):
        if self.data_map.get(tr_id, None) is None:
            self.data_map[tr_id] = {"columns": [], "encrypt": False, "key": None, "iv": None}

        if columns is not None:
            self.data_map[tr_id]["columns"] = columns

        if encrypt is not None:
            self.data_map[tr_id]["encrypt"] = encrypt

        if key is not None:
            self.data_map[tr_id]["key"] = key

        if iv is not None:
            self.data_map[tr_id]["iv"] = iv

    # private
    async def __subscriber(self, ws: websockets.ClientConnection):
        async for raw in ws:
            logging.info("received message >> %s" % raw)
            show_result = False

            df = pd.DataFrame()

            if raw[0] in ["0", "1"]:
                d1 = raw.split("|")
                if len(d1) < 4:
                    raise ValueError("data not found...")

                tr_id = d1[1]

                dm = self.data_map[tr_id]
                d = d1[3]
                if dm.get("encrypt", None) == "Y":
                    d = self.aes_cbc_base64_dec(dm["key"], dm["iv"], d)

                df = pd.read_csv(
                    StringIO(d), header=None, sep="^", names=dm["columns"], dtype=object
                )

                show_result = True

            else:
                rsp = self.system_resp(raw)

                tr_id = rsp.tr_id
                self.add_data_map(
                    tr_id=rsp.tr_id, encrypt=rsp.encrypt, key=rsp.ekey, iv=rsp.iv
                )

                if rsp.isPingPong:
                    print(f"### RECV [PINGPONG] [{raw}]")
                    await ws.pong(raw)
                    print(f"### SEND [PINGPONG] [{raw}]")

                if self.result_all_data:
                    show_result = True

            if show_result is True and self.on_result is not None:
                self.on_result(ws, tr_id, df, self.data_map[tr_id])

    async def __runner(self):
        if len(self.open_map.keys()) > 40:
            raise ValueError("Subscription's max is 40")

        url = f"{settings.KIS_WS_URL}{self.api_url}"

        while self.retry_count < self.max_retries:
            try:
                async with websockets.connect(url) as ws:
                    # request subscribe
                    for name, obj in self.open_map.items():
                        await self.send_multiple(
                            ws, obj["func"], "1", obj["items"], obj["kwargs"]
                        )

                    # subscriber
                    await asyncio.gather(
                        self.__subscriber(ws),
                    )
            except Exception as e:
                print("Connection exception >> ", e)
                self.retry_count += 1
                await asyncio.sleep(1)

    # func
    async def send(
            self,
            ws: websockets.ClientConnection,
            request: Callable[[str, str, ...], (dict, list[str])],
            tr_type: str,
            data: str,
            kwargs: dict = None,
    ):
        k = {} if kwargs is None else kwargs
        msg, columns = request(tr_type, data, **k)

        self.add_data_map(tr_id=msg["body"]["input"]["tr_id"], columns=columns)

        logging.info("send message >> %s" % json.dumps(msg))

        await ws.send(json.dumps(msg))
        self.smart_sleep()

    async def send_multiple(
            self,
            ws: websockets.ClientConnection,
            request: Callable[[str, str, ...], (dict, list[str])],
            tr_type: str,
            data: list | str,
            kwargs: dict = None,
    ):
        if type(data) is str:
            await self.send(ws, request, tr_type, data, kwargs)
        elif type(data) is list:
            for d in data:
                await self.send(ws, request, tr_type, d, kwargs)
        else:
            raise ValueError("data must be str or list")

    def subscribe(
            self,
            request: Callable[[str, str, ...], (dict, list[str])],
            data: list | str,
            kwargs: dict = None,
    ):
        self.add_open_map(request.__name__, request, data, kwargs)

    def unsubscribe(
            self,
            ws: websockets.ClientConnection,
            request: Callable[[str, str, ...], (dict, list[str])],
            data: list | str,
    ):
        self.send_multiple(ws, request, "2", data)

    # start
    def start(
            self,
            on_result: Callable[
                [websockets.ClientConnection, str, pd.DataFrame, dict], None
            ],
            result_all_data: bool = False,
    ):
        self.on_result = on_result
        self.result_all_data = result_all_data
        try:
            asyncio.run(self.__runner())
        except KeyboardInterrupt:
            print("Closing by KeyboardInterrupt")
