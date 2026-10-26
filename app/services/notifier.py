import logging
import smtplib
from email.message import EmailMessage

import httpx

from app.config import NTFY_URL, SMTP_FROM, SMTP_HOST, SMTP_PASS, SMTP_PORT, SMTP_TO, SMTP_USER

logger = logging.getLogger(__name__)


def _send_email(subject, body):
    if not SMTP_HOST:
        logger.info("SMTP not configured; dry-run email: %s\n%s", subject, body)
        return
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = SMTP_TO
        msg.set_content(body)
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
            s.starttls()
            if SMTP_USER:
                s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
    except Exception as e:
        logger.error("email send failed: %s", e)


def _ntfy(title, body):
    if not NTFY_URL:
        return
    try:
        httpx.post(NTFY_URL, content=body, headers={"Title": title}, timeout=10)
    except Exception as e:
        logger.error("ntfy push failed: %s", e)


def notify_new_game(game):
    subject = f"New free game: {game.get('title')}"
    body = (
        f"{game.get('title')}\n"
        f"Platform: {game.get('platform')}\n"
        f"Source: {game.get('source')}\n"
        f"URL: {game.get('url')}\n"
        f"Ends: {game.get('end_date')}\n"
    )
    _send_email(subject, body)
    _ntfy(subject, body)


def notify_wishlist(game):
    subject = f"Wishlist match free: {game.get('title')}"
    body = (
        f"{game.get('title')} is now free and matches your wishlist.\n"
        f"Platform: {game.get('platform')}\n"
        f"Source: {game.get('source')}\n"
        f"URL: {game.get('url')}\n"
        f"Ends: {game.get('end_date')}\n"
    )
    _send_email(subject, body)
    _ntfy(subject, body)


def notify_reminder(game):
    subject = f"Expiring soon: {game.get('title')}"
    body = (
        f"{game.get('title')} ends in ~2 hours.\n"
        f"Platform: {game.get('platform')}\n"
        f"URL: {game.get('url')}\n"
        f"Ends: {game.get('end_date')}\n"
    )
    _send_email(subject, body)
    _ntfy(subject, body)
