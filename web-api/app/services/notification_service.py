"""
알림 서비스
===========
- 이메일 알림
- 슬랙 웹훅
- 푸시 알림 (FCM)
"""

import httpx
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from abc import ABC, abstractmethod

from app.core.config import get_settings
from app.schemas.printer import Notification, NotificationType

logger = logging.getLogger(__name__)


class NotificationSender(ABC):
    """알림 발송 추상 클래스"""
    
    @abstractmethod
    async def send(self, notification: Notification) -> bool:
        """알림 발송"""
        pass
    
    @abstractmethod
    def is_configured(self) -> bool:
        """설정 완료 여부"""
        pass


class EmailNotificationSender(NotificationSender):
    """이메일 알림 발송"""
    
    def __init__(self):
        self.settings = get_settings()
    
    def is_configured(self) -> bool:
        return bool(
            self.settings.SMTP_HOST and
            self.settings.SMTP_USER and
            self.settings.NOTIFICATION_EMAIL_TO
        )
    
    async def send(self, notification: Notification) -> bool:
        if not self.is_configured():
            return False
        
        try:
            # 이메일 내용 구성
            msg = MIMEMultipart("alternative")
            msg["Subject"] = notification.title
            msg["From"] = self.settings.SMTP_USER
            msg["To"] = ", ".join(self.settings.NOTIFICATION_EMAIL_TO)
            
            # HTML 본문
            html_body = self._build_html_body(notification)
            msg.attach(MIMEText(html_body, "html"))
            
            # 발송
            with smtplib.SMTP(self.settings.SMTP_HOST, self.settings.SMTP_PORT) as server:
                server.starttls()
                if self.settings.SMTP_PASSWORD:
                    server.login(self.settings.SMTP_USER, self.settings.SMTP_PASSWORD)
                server.sendmail(
                    self.settings.SMTP_USER,
                    self.settings.NOTIFICATION_EMAIL_TO,
                    msg.as_string()
                )
            
            logger.info(f"📧 이메일 알림 발송 완료: {notification.title}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 이메일 발송 실패: {e}")
            return False
    
    def _build_html_body(self, notification: Notification) -> str:
        """HTML 이메일 본문 생성"""
        
        # 알림 유형별 색상
        color_map = {
            NotificationType.PRINT_COMPLETE: "#28a745",  # 녹색
            NotificationType.PRINT_ERROR: "#dc3545",     # 빨강
            NotificationType.LOW_RESIN: "#ffc107",       # 노랑
            NotificationType.PRINTER_OFFLINE: "#6c757d", # 회색
        }
        color = color_map.get(notification.type, "#007bff")
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
                .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                .header {{ background: {color}; color: white; padding: 20px; text-align: center; }}
                .header h1 {{ margin: 0; font-size: 24px; }}
                .content {{ padding: 30px; }}
                .info-box {{ background: #f8f9fa; border-radius: 6px; padding: 15px; margin: 15px 0; }}
                .label {{ color: #666; font-size: 12px; text-transform: uppercase; margin-bottom: 5px; }}
                .value {{ font-size: 16px; font-weight: 500; }}
                .footer {{ background: #f8f9fa; padding: 15px; text-align: center; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{notification.title}</h1>
                </div>
                <div class="content">
                    <p style="font-size: 16px; color: #333; line-height: 1.6;">
                        {notification.message}
                    </p>
                    
                    <div class="info-box">
                        <div class="label">프린터</div>
                        <div class="value">{notification.printer_name} ({notification.printer_serial})</div>
                    </div>
                    
                    {f'''
                    <div class="info-box">
                        <div class="label">작업명</div>
                        <div class="value">{notification.job_name}</div>
                    </div>
                    ''' if notification.job_name else ''}
                    
                    <div class="info-box">
                        <div class="label">시간</div>
                        <div class="value">{notification.timestamp.strftime('%Y-%m-%d %H:%M:%S')}</div>
                    </div>
                </div>
                <div class="footer">
                    오리누 3D프린터 원격제어 시스템
                </div>
            </div>
        </body>
        </html>
        """


class SlackNotificationSender(NotificationSender):
    """슬랙 웹훅 알림"""
    
    def __init__(self):
        self.settings = get_settings()
    
    def is_configured(self) -> bool:
        return bool(self.settings.SLACK_WEBHOOK_URL)
    
    async def send(self, notification: Notification) -> bool:
        if not self.is_configured():
            return False
        
        try:
            # 알림 유형별 이모지
            emoji_map = {
                NotificationType.PRINT_COMPLETE: "✅",
                NotificationType.PRINT_ERROR: "🚨",
                NotificationType.LOW_RESIN: "⚠️",
                NotificationType.PRINTER_OFFLINE: "🔴",
            }
            emoji = emoji_map.get(notification.type, "📢")
            
            # 슬랙 메시지 페이로드
            payload = {
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"{emoji} {notification.title}"
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": notification.message
                        }
                    },
                    {
                        "type": "section",
                        "fields": [
                            {
                                "type": "mrkdwn",
                                "text": f"*프린터:*\n{notification.printer_name}"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*시간:*\n{notification.timestamp.strftime('%Y-%m-%d %H:%M')}"
                            }
                        ]
                    }
                ]
            }
            
            if notification.job_name:
                payload["blocks"].insert(2, {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*작업명:* {notification.job_name}"
                    }
                })
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.settings.SLACK_WEBHOOK_URL,
                    json=payload,
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    logger.info(f"💬 슬랙 알림 발송 완료: {notification.title}")
                    return True
                else:
                    logger.error(f"❌ 슬랙 발송 실패: {response.status_code}")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ 슬랙 발송 오류: {e}")
            return False


class FCMNotificationSender(NotificationSender):
    """Firebase Cloud Messaging 푸시 알림"""
    
    def __init__(self):
        self.settings = get_settings()
        self.fcm_url = "https://fcm.googleapis.com/fcm/send"
    
    def is_configured(self) -> bool:
        return bool(self.settings.FCM_SERVER_KEY)
    
    async def send(self, notification: Notification, device_token: Optional[str] = None) -> bool:
        """
        FCM 푸시 알림 발송
        
        Args:
            notification: 알림 정보
            device_token: FCM 디바이스 토큰 (None이면 토픽으로 발송)
        """
        if not self.is_configured():
            return False
        
        try:
            payload = {
                "notification": {
                    "title": notification.title,
                    "body": notification.message,
                },
                "data": {
                    "type": notification.type.value,
                    "printer_serial": notification.printer_serial,
                    "printer_name": notification.printer_name,
                    "timestamp": notification.timestamp.isoformat(),
                }
            }
            
            # 특정 디바이스 또는 토픽으로 발송
            if device_token:
                payload["to"] = device_token
            else:
                # 모든 구독자에게 발송 (토픽)
                payload["to"] = "/topics/printer_notifications"
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.fcm_url,
                    json=payload,
                    headers={
                        "Authorization": f"key={self.settings.FCM_SERVER_KEY}",
                        "Content-Type": "application/json"
                    },
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    logger.info(f"📱 FCM 푸시 발송 완료: {notification.title}")
                    return True
                else:
                    logger.error(f"❌ FCM 발송 실패: {response.status_code}")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ FCM 발송 오류: {e}")
            return False


class NotificationService:
    """
    통합 알림 서비스
    
    설정된 모든 채널로 알림 발송
    """
    
    def __init__(self):
        self.senders = [
            EmailNotificationSender(),
            SlackNotificationSender(),
            FCMNotificationSender(),
        ]
    
    async def send_notification(self, notification: Notification) -> dict:
        """
        모든 설정된 채널로 알림 발송
        
        Returns:
            dict: 채널별 발송 결과
        """
        results = {}
        
        for sender in self.senders:
            channel_name = sender.__class__.__name__.replace("NotificationSender", "")
            
            if sender.is_configured():
                try:
                    success = await sender.send(notification)
                    results[channel_name] = "success" if success else "failed"
                except Exception as e:
                    results[channel_name] = f"error: {e}"
            else:
                results[channel_name] = "not_configured"
        
        return results
    
    def get_configured_channels(self) -> list:
        """설정된 알림 채널 목록"""
        return [
            sender.__class__.__name__.replace("NotificationSender", "")
            for sender in self.senders
            if sender.is_configured()
        ]


# 전역 서비스 인스턴스
_notification_service: Optional[NotificationService] = None


def get_notification_service() -> NotificationService:
    """알림 서비스 싱글톤 반환"""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service


async def notification_handler(notification: Notification):
    """
    폴링 서비스에서 호출될 알림 핸들러
    
    Usage:
        polling_service.on_notification(notification_handler)
    """
    service = get_notification_service()
    results = await service.send_notification(notification)
    logger.info(f"알림 발송 결과: {results}")
