#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
한국투자증권 API 연동 테스트
- 토큰 발급
- 잔고 조회
- 현재가 조회
"""

import requests
import yaml
import sys
from datetime import datetime

print("=" * 80)
print("한국투자증권 API 연동 테스트")
print("=" * 80)

# 1. 설정 파일 읽기
print("\n[1단계] kis_devlp.yaml 읽기...")
try:
    with open("kis_devlp.yaml", encoding="UTF-8") as f:
        cfg = yaml.load(f, yaml.FullLoader)
    print("✅ 설정 파일 읽기 성공")
except Exception as e:
    print(f"❌ 설정 파일 읽기 실패: {e}")
    sys.exit(1)

# 2. 모의투자/실전투자 선택
print("\n[2단계] 서버 선택...")
print("1: 실전투자")
print("2: 모의투자")
choice = input("선택 (1 or 2): ").strip()

if choice == "1":
    base_url = cfg["prod"]
    app_key = cfg["my_app"]
    app_secret = cfg["my_sec"]
    account = cfg["my_acct_stock"]
    print("✅ 실전투자 서버 선택")
elif choice == "2":
    base_url = cfg["vps"]
    app_key = cfg["paper_app"]
    app_secret = cfg["paper_sec"]
    account = cfg["my_paper_stock"]
    print("✅ 모의투자 서버 선택")
else:
    print("❌ 잘못된 선택")
    sys.exit(1)

product = cfg["my_prod"]

# 3. 토큰 발급
print("\n[3단계] 토큰 발급...")
token_url = f"{base_url}/oauth2/tokenP"
token_body = {
    "grant_type": "client_credentials",
    "appkey": app_key,
    "appsecret": app_secret
}

try:
    res = requests.post(token_url, json=token_body)
    print(f"Status Code: {res.status_code}")
    
    if res.status_code == 200:
        token_data = res.json()
        access_token = token_data["access_token"]
        expire_time = token_data["access_token_token_expired"]
        print(f"✅ 토큰 발급 성공!")
        print(f"   토큰: {access_token[:50]}...")
        print(f"   만료: {expire_time}")
    else:
        print(f"❌ 토큰 발급 실패")
        print(f"   응답: {res.text}")
        sys.exit(1)
except Exception as e:
    print(f"❌ 토큰 발급 오류: {e}")
    sys.exit(1)

# 4. 잔고 조회
print("\n[4단계] 잔고 조회...")
balance_url = f"{base_url}/uapi/domestic-stock/v1/trading/inquire-balance"

if choice == "1":
    tr_id = "TTTC8434R"
elif choice == "2":
    tr_id = "VTTC8434R"

headers = {
    "Content-Type": "application/json",
    "authorization": f"Bearer {access_token}",
    "appkey": app_key,
    "appsecret": app_secret,
    "tr_id": tr_id,
    "custtype": "P"
}

params = {
    "CANO": account,
    "ACNT_PRDT_CD": product,
    "AFHR_FLPR_YN": "N",
    "INQR_DVSN": "02",  # 종목별
    "UNPR_DVSN": "01",
    "FUND_STTL_ICLD_YN": "N",
    "FNCG_AMT_AUTO_RDPT_YN": "N",
    "PRCS_DVSN": "00",
    "CTX_AREA_FK100": "",
    "CTX_AREA_NK100": ""
}

try:
    res = requests.get(balance_url, headers=headers, params=params)
    print(f"Status Code: {res.status_code}")
    
    if res.status_code == 200:
        data = res.json()
        
        if data["rt_cd"] == "0":
            print("✅ 잔고 조회 성공!")
            
            # 계좌 요약
            output2 = data["output2"][0] if data["output2"] else {}
            total_buy_amt = output2.get("pchs_amt_smtl_amt", "0")  # 총 매입금액
            total_eval_amt = output2.get("evlu_amt_smtl_amt", "0")  # 총 평가금액
            total_profit = output2.get("evlu_pfls_smtl_amt", "0")  # 총 평가손익
            cash = output2.get("dnca_tot_amt", "0")  # 예수금
            
            print(f"\n   💰 계좌 요약:")
            print(f"   - 예수금: {int(cash):,}원")
            print(f"   - 총 매입금액: {int(total_buy_amt):,}원")
            print(f"   - 총 평가금액: {int(total_eval_amt):,}원")
            print(f"   - 총 평가손익: {int(total_profit):,}원")
            
            # 보유 종목
            output1 = data["output1"]
            if output1:
                print(f"\n   📊 보유 종목 ({len(output1)}개):")
                for stock in output1:
                    code = stock.get("pdno", "")
                    name = stock.get("prdt_name", "")
                    qty = stock.get("hldg_qty", "0")
                    avg_price = stock.get("pchs_avg_pric", "0")
                    current_price = stock.get("prpr", "0")
                    profit = stock.get("evlu_pfls_amt", "0")
                    profit_rate = stock.get("evlu_pfls_rt", "0")
                    
                    if int(qty) > 0:
                        print(f"\n   [{code}] {name}")
                        print(f"      보유: {int(qty):,}주")
                        print(f"      매입가: {float(avg_price):,.0f}원")
                        print(f"      현재가: {float(current_price):,.0f}원")
                        print(f"      평가손익: {int(profit):,}원 ({float(profit_rate):.2f}%)")
            else:
                print("\n   📊 보유 종목: 없음")
        else:
            print(f"❌ 잔고 조회 실패")
            print(f"   메시지: {data['msg1']}")
    else:
        print(f"❌ 잔고 조회 실패")
        print(f"   응답: {res.text}")
except Exception as e:
    print(f"❌ 잔고 조회 오류: {e}")

# 5. 삼성전자 현재가 조회
print("\n[5단계] 삼성전자(005930) 현재가 조회...")
price_url = f"{base_url}/uapi/domestic-stock/v1/quotations/inquire-price"

headers = {
    "Content-Type": "application/json",
    "authorization": f"Bearer {access_token}",
    "appkey": app_key,
    "appsecret": app_secret,
    "tr_id": "FHKST01010100",
    "custtype": "P"
}

params = {
    "FID_COND_MRKT_DIV_CODE": "J",
    "FID_INPUT_ISCD": "005930"
}

try:
    res = requests.get(price_url, headers=headers, params=params)
    print(f"Status Code: {res.status_code}")
    
    if res.status_code == 200:
        data = res.json()
        
        if data["rt_cd"] == "0":
            output = data["output"]
            
            code = output.get("stck_shrn_iscd", "")
            name = output.get("prdt_abrv_name", "")
            price = output.get("stck_prpr", "0")
            change = output.get("prdy_vrss", "0")
            change_rate = output.get("prdy_ctrt", "0")
            volume = output.get("acml_vol", "0")
            
            print(f"✅ 현재가 조회 성공!")
            print(f"\n   📈 [{code}] {name}")
            print(f"   - 현재가: {int(price):,}원")
            print(f"   - 전일대비: {int(change):,}원 ({float(change_rate):.2f}%)")
            print(f"   - 거래량: {int(volume):,}주")
        else:
            print(f"❌ 현재가 조회 실패")
            print(f"   메시지: {data['msg1']}")
    else:
        print(f"❌ 현재가 조회 실패")
        print(f"   응답: {res.text}")
except Exception as e:
    print(f"❌ 현재가 조회 오류: {e}")

print("\n" + "=" * 80)
print("테스트 완료!")
print("=" * 80)
