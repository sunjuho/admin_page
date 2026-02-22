import copy
import json
import time
from collections import namedtuple
from datetime import datetime

import requests
from django.conf import settings  # 유저 모델 참조용
from django.utils import timezone

from investments.models import Account, Token


class KisAuth:
    def __init__(self, account: Account):
        self.account = account

        self._TRENV = tuple()
        self._autoReAuth = True  # url_fetch 시 자동 재인증 여부
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
