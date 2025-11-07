__version__ = (1, 0, 0)
# meta developer: @dealdoxer

from herokutl.types import Message
from .. import loader, utils
import asyncio
import os
import tempfile
import requests
import traceback

DEFAULT_IMGBB_KEY = "f103699f3cdc973fc299f0cb0b8a60b0"

@loader.tds
class GetImageURL(loader.Module):
    """Загружает прикреплённую картинку на imgbb и возвращает ссылку"""
    strings = {"name": "GetImageURL"}
    strings_ru = {"name": "GetImageURL"}

    def __init__(self):
        self.config = loader.ModuleConfig(
            "IMGBB_API_KEY", DEFAULT_IMGBB_KEY, "Ключ imgbb API (https://api.imgbb.com/) (можно установить командой / inline mode)"
        )
        self._client = None
        self._db = None

    async def client_ready(self, client, db):
        self._client = client
        self._db = db

    def _get_saved_key(self):
        try:
            cfg_key = self.config.get("IMGBB_API_KEY", None)
        except Exception:
            try:
                cfg_key = self.config["IMGBB_API_KEY"]
            except Exception:
                cfg_key = None

        if cfg_key:
            return cfg_key

        key = self.get("imgbb_api_key")
        if key:
            return key

        env_key = os.environ.get("IMGBB_API_KEY")
        if env_key:
            return env_key

        return DEFAULT_IMGBB_KEY

    @loader.command(ru_doc="Установить ключ imgbb API: .setimgbbkey <API_KEY>")
    async def setimgbbkeycmd(self, message: Message):
        args = utils.get_args_raw(message)
        if not args:
            await utils.answer(message, "<b>❗ Укажите API ключ. Пример:</b>\n.setimgbbkey f1036....", parse_mode="HTML")
            return
        key = args.strip()
        self.set("imgbb_api_key", key)
        try:
            self.config["IMGBB_API_KEY"] = key
        except Exception:
            pass
        await utils.answer(message, "<b>✅ Ключ imgbb сохранён.</b>", parse_mode="HTML")

    def _upload_sync(self, file_path: str, api_key: str) -> str:
        url = "https://api.imgbb.com/1/upload"
        with open(file_path, "rb") as f:
            img_data = f.read()
        payload = {
            "key": api_key,
        }
        files = {
            "image": img_data
        }
        resp = requests.post(url, data=payload, files=files, timeout=60)
        resp.raise_for_status()
        result = resp.json()
        if result.get("success"):
            data = result.get("data", {})
            return data.get("url") or data.get("display_url") or (data.get("image") or {}).get("url")
        else:
            raise Exception("Upload failed: " + str(result))

    @loader.command(ru_doc="Получить URL изображения: прикрепите картинку (или ответьте на неё)")
    async def getimgurl(self, message: Message):
        """
        Команда .getimgurl
        Поддерживает:
        - Отправку команды как reply на сообщение с картинкой.
        - Отправку команды в сообщении, в котором сама прикреплена картинка (caption + фото).
        """
        try:
            api_key = self._get_saved_key()
            if not api_key:
                await utils.answer(
                    message,
                    "<b>❌ API ключ imgbb не найден.</b>\nВы можете сохранить его командой:\n.setimgbbkey <API_KEY>\nИли задать в настройках модуля (inline-mode).",
                    parse_mode="HTML"
                )
                return

            target_msg = None
            if message.reply_to:
                target_msg = await message.get_reply_message()
            else:
                if getattr(message, "media", None):
                    target_msg = message

            if not target_msg or not getattr(target_msg, "media", None):
                await utils.answer(message, "<b>❗ Пожалуйста, прикрепите изображение или ответьте на сообщение с изображением и вызовите команду.</b>", parse_mode="HTML")
                return

            processing = await utils.answer(message, "<b>📤 Загружаю картинку на imgbb...</b>", parse_mode="HTML")

            # скачиваем файл во временный файл
            tmp = tempfile.NamedTemporaryFile(suffix=".img", delete=False)
            tmp.close()
            tmp_path = tmp.name

            try:
                await self._client.download_media(target_msg, file=tmp_path)
            except Exception as e:
                await processing.edit(f"<b>❌ Ошибка при загрузке медиа:</b>\n<code>{utils.escape_html(str(e))}</code>", parse_mode="HTML")
                try:
                    os.unlink(tmp_path)
                except:
                    pass
                return

            loop = asyncio.get_event_loop()
            try:
                url = await loop.run_in_executor(None, self._upload_sync, tmp_path, api_key)
            except Exception as e:
                tb = traceback.format_exc()
                await processing.edit(f"<b>❌ Ошибка при загрузке на imgbb:</b>\n<code>{utils.escape_html(str(e))}</code>", parse_mode="HTML")
                try:
                    os.unlink(tmp_path)
                except:
                    pass
                print("Upload to imgbb failed:", tb)
                return

            try:
                os.unlink(tmp_path)
            except:
                pass

            # отправляем результат
            text = f"<b>✅ Картинка загружена:</b>\n<b>URL:</b> <code>{utils.escape_html(url)}</code>"
            try:
                await processing.edit(text, parse_mode="HTML")
            except:
                await utils.answer(message, text, parse_mode="HTML")

        except Exception as e:
            tb = traceback.format_exc()
            print("Error in getimgurl:", tb)
            await utils.answer(message, f"<b>❌ Внутренняя ошибка:</b>\n<code>{utils.escape_html(str(e))}</code>", parse_mode="HTML")