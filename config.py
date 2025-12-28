"""
업비트 API 설정 파일
.env 파일에 API 키를 저장하거나, 직접 여기에 입력하세요.
"""
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 업비트 API 키 설정
ACCESS_KEY = os.getenv('UPBIT_ACCESS_KEY', '[input your upbit api key]')
SECRET_KEY = os.getenv('UPBIT_SECRET_KEY', '[input your upbit api key]')

# Gemini API 키 설정
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')

# API 키가 설정되지 않았을 경우 직접 입력 (보안상 권장하지 않음)
if not ACCESS_KEY or not SECRET_KEY:
    print("⚠️  .env 파일에 API 키가 없습니다.")
    print("   .env 파일을 생성하거나 config.py에서 직접 설정하세요.")
    # 여기에 직접 입력할 수도 있습니다 (보안상 권장하지 않음)
    # ACCESS_KEY = "your_access_key_here"
    # SECRET_KEY = "your_secret_key_here"

