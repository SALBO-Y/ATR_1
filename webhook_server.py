#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
트레이딩뷰 Webhook → 텔레그램 중계 서버
- Flask 기반 웹서버
- 트레이딩뷰 알림 수신
- 텔레그램으로 자동 전송
"""

from flask import Flask, request, jsonify
import requests
import json
import logging
from datetime import datetime

app = Flask(__name__)

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# 설정 (직접 입력)
# ============================================================================
TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"
WEBHOOK_SECRET = "your-secret-key-12345"  # 보안용 (트레이딩뷰에서도 동일하게 설정)

# ============================================================================
# 텔레그램 전송 함수
# ============================================================================
def send_telegram_message(text):
    """텔레그램 메시지 전송"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML"
        }
        
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"✅ 텔레그램 전송 성공: {text[:50]}...")
            return True
        else:
            logger.error(f"❌ 텔레그램 전송 실패: {response.status_code}")
            return False
    
    except Exception as e:
        logger.error(f"❌ 텔레그램 전송 오류: {e}")
        return False


# ============================================================================
# Webhook 엔드포인트
# ============================================================================
@app.route('/webhook', methods=['POST'])
def tradingview_webhook():
    """
    트레이딩뷰 Webhook 수신
    
    예상 JSON 형식:
    {
        "secret": "your-secret-key-12345",
        "action": "buy",
        "ticker": "005930",
        "name": "삼성전자",
        "price": 60000,
        "strategy": "골든크로스"
    }
    """
    
    try:
        # 1. 데이터 파싱
        data = request.json
        logger.info(f"📨 Webhook 수신: {json.dumps(data, ensure_ascii=False)}")
        
        # 2. 보안 검증
        if data.get('secret') != WEBHOOK_SECRET:
            logger.warning("⚠️ 잘못된 시크릿 키")
            return jsonify({"error": "Unauthorized"}), 401
        
        # 3. 필수 필드 확인
        if 'action' not in data or 'ticker' not in data:
            logger.error("❌ 필수 필드 누락")
            return jsonify({"error": "Missing required fields"}), 400
        
        # 4. 텔레그램 메시지 생성
        action = data['action'].upper()
        ticker = data['ticker']
        name = data.get('name', ticker)
        price = data.get('price', 0)
        strategy = data.get('strategy', '알림')
        
        message = f"""
🔔 <b>트레이딩뷰 알림</b>

동작: {action}
종목: {name} ({ticker})
가격: {price:,.0f}원
전략: {strategy}
시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

자동매매 명령:
<code>{action} {ticker} {name}</code>
"""
        
        # 5. 텔레그램 전송
        success = send_telegram_message(message)
        
        if success:
            return jsonify({
                "status": "success",
                "message": "Alert forwarded to Telegram"
            }), 200
        else:
            return jsonify({
                "status": "error",
                "message": "Failed to send Telegram message"
            }), 500
    
    except Exception as e:
        logger.error(f"❌ Webhook 처리 오류: {e}")
        return jsonify({"error": str(e)}), 500


# ============================================================================
# 헬스 체크
# ============================================================================
@app.route('/health', methods=['GET'])
def health_check():
    """서버 상태 확인"""
    return jsonify({
        "status": "running",
        "timestamp": datetime.now().isoformat()
    }), 200


# ============================================================================
# 메인
# ============================================================================
if __name__ == '__main__':
    print("=" * 80)
    print("트레이딩뷰 Webhook → 텔레그램 중계 서버")
    print("=" * 80)
    print(f"\n🔑 Webhook Secret: {WEBHOOK_SECRET}")
    print(f"📡 Webhook URL: http://YOUR_SERVER_IP:5000/webhook")
    print(f"💬 Telegram Chat ID: {TELEGRAM_CHAT_ID}")
    print("\n서버 시작 중...\n")
    
    # 0.0.0.0으로 바인딩 (외부 접속 허용)
    app.run(host='0.0.0.0', port=5000, debug=False)
