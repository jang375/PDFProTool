"""
ai_manager.py — Wrapper for Gemini API
Manages API keys and handles requests to Google's Gemini models.
"""

from __future__ import annotations

import logging
from PyQt6.QtCore import QSettings

try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False
    logging.warning("google-genai package is not installed.")

class AIManager:
    """Manager for Gemini AI interactions."""
    
    def __init__(self):
        self.settings = QSettings("PDFProTool", "Settings")
        self.client = None
        self._init_client()
        
    def _init_client(self):
        """Initializes the Gemini client from stored settings."""
        if not HAS_GENAI:
            logging.warning("google-genai not available; AI features disabled.")
            return

        api_key = self.settings.value("gemini_api_key", "", type=str)
        if api_key:
            try:
                self.client = genai.Client(api_key=api_key)
                logging.info("Gemini client initialized successfully.")
            except Exception as e:
                logging.error(f"Failed to initialize Gemini client: {e}")
                self.client = None
        else:
            logging.info("No Gemini API key found in settings.")
            self.client = None
            
    def update_api_key(self, api_key: str):
        """Updates and stores the API key, then re-initializes the client."""
        self.settings.setValue("gemini_api_key", api_key)
        self.settings.sync()
        self._init_client()
        
    def is_configured(self) -> bool:
        """Returns True if the client is ready to make requests."""
        return self.client is not None
        
    def extract_table(self, image_bytes: bytes) -> str:
        """
        Extracts a table from the given image bytes and returns it as a CSV string.
        """
        if not self.is_configured():
            raise ValueError("Gemini API Key가 설정되지 않았습니다. 환경설정에서 API 키를 입력해주세요.")
            
        prompt = (
            "이 이미지에 있는 표 데이터를 분석해서 CSV 형식으로 변환해줘. "
            "다른 부연 설명이나 마크다운 코드 블록(```csv) 없이 오직 CSV 데이터 텍스트만 출력해줘."
        )
        
        try:
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[
                    prompt, 
                    types.Part.from_bytes(data=image_bytes, mime_type='image/png')
                ]
            )
            return response.text.strip()
        except Exception as e:
            logging.error(f"Gemini API error during table extraction: {e}")
            raise Exception(f"AI 표 추출 실패: {e}")

    def correct_ocr(self, text: str) -> str:
        """
        Corrects typos in the given OCR-extracted text based on context.
        """
        if not self.is_configured():
            raise ValueError("Gemini API Key가 설정되지 않았습니다. 환경설정에서 API 키를 입력해주세요.")
            
        prompt = (
            "다음은 OCR을 통해 추출한 텍스트야. 간혹 1을 I로 읽거나 0을 O로 읽는 등의 오타가 있을 수 있어. "
            "문맥에 맞게 오타를 자연스럽게 수정해줘. "
            "수정된 텍스트만 출력하고, 불필요한 부연 설명은 하지 마.\n\n"
            f"{text}"
        )
        
        try:
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            return response.text.strip()
        except Exception as e:
            logging.error(f"Gemini API error during OCR correction: {e}")
            raise Exception(f"AI 오타 교정 실패: {e}")
            
    def summarize_text(self, text: str) -> str:
        """
        Summarizes the given text.
        """
        if not self.is_configured():
            raise ValueError("Gemini API Key가 설정되지 않았습니다. 환경설정에서 API 키를 입력해주세요.")
            
        prompt = f"다음 텍스트의 핵심 내용을 한국어로 명확하게 요약해줘:\n\n{text}"
        
        try:
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            return response.text.strip()
        except Exception as e:
            logging.error(f"Gemini API error during text summarization: {e}")
            raise Exception(f"AI 요약 실패: {e}")

    def create_chat_session(self, context_text: str = ""):
        """
        Creates and returns a new Gemini chat session, optionally seeded with context.
        """
        if not self.is_configured():
            raise ValueError("Gemini API Key가 설정되지 않았습니다. 환경설정에서 API 키를 입력해주세요.")
            
        try:
            # We can use system instructions if the model supports it, or just send a first message.
            # gemini-2.5-flash supports system_instructions.
            config = None
            if context_text:
                config = types.GenerateContentConfig(
                    system_instruction=f"너는 PDF 문서 분석 어시스턴트야. 다음은 현재 사용자가 보고 있는 문서의 내용이야:\n\n{context_text}\n\n이 내용을 바탕으로 사용자의 질문에 친절하고 정확하게 답변해줘. 문서에 없는 내용이라면 모른다고 답변해."
                )
                
            chat = self.client.chats.create(
                model='gemini-2.5-flash',
                config=config
            )
            return chat
        except Exception as e:
            logging.error(f"Gemini API error creating chat session: {e}")
            raise Exception(f"AI 채팅 세션 생성 실패: {e}")
