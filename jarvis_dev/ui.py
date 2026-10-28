"""Native PySide6 desktop interface for L.I.N.G.O."""
from __future__ import annotations

import os
import threading
from pathlib import Path

from PySide6.QtCore import QThread, Signal, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from .ai import JarvisAssistant
from .data import DataStore
from .projects import ProjectService
from .speech import record_wav, transcribe_wav


class CommandWorker(QThread):
    progress = Signal(str)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, assistant: JarvisAssistant, text: str, attachments: list[dict]):
        super().__init__()
        self.assistant = assistant
        self.text = text
        self.attachments = attachments

    def run(self):
        try:
            self.completed.emit(self.assistant.respond(self.text, self.progress.emit, self.attachments))
        except Exception as exc:
            self.failed.emit(str(exc))


class SpeechWorker(QThread):
    progress = Signal(str)
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, api_key: str):
        super().__init__()
        self.api_key = api_key
        self.stop_event = threading.Event()

    def request_stop(self):
        self.stop_event.set()

    def run(self):
        try:
            audio = record_wav(self.stop_event, self.progress.emit)
            self.progress.emit("Enviando áudio para transcrição")
            self.completed.emit(transcribe_wav(audio, self.api_key))
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self, project_root: Path):
        super().__init__()
        self.setWindowTitle("L.I.N.G.O.  |  Assistente inteligente")
        self.setMinimumSize(890, 625)
        self.resize(1190, 780)
        self.storage = DataStore()
        self.assistant = JarvisAssistant(ProjectService(project_root), media_dir=self.storage.media_dir)
        self.activity = self.storage.record_daily_use()
        self.active_chat_id: str | None = None
        self.pending_media: list[dict] = []
        self.welcome_widget: QWidget | None = None
        self.command_worker: CommandWorker | None = None
        self.speech_worker: SpeechWorker | None = None
        self._build_ui()
        self._populate_chats()
        existing = self.storage.chats()
        self._open_chat(existing[0]["id"] if existing else self.storage.new_chat()["id"])
        self._set_status("Disponível")

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # LEFT: conversations and learning streak
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(278)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(19, 26, 19, 23)
        side.setSpacing(14)

        brand_row = QHBoxLayout()
        logo = QLabel("L")
        logo.setObjectName("logo")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedSize(45, 45)
        brand_row.addWidget(logo)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(2)
        brand = QLabel("L.I.N.G.O.")
        brand.setObjectName("brand")
        brand_text.addWidget(brand)
        brand_caption = QLabel("INTELLIGENT LEARNING")
        brand_caption.setObjectName("brandCaption")
        brand_text.addWidget(brand_caption)
        brand_row.addLayout(brand_text)
        brand_row.addStretch()
        side.addLayout(brand_row)
        side.addSpacing(16)

        self.new_button = QPushButton("＋   Nova conversa")
        self.new_button.setObjectName("newChatButton")
        self.new_button.setMinimumHeight(46)
        self.new_button.clicked.connect(self._new_chat)
        side.addWidget(self.new_button)
        conversations_label = QLabel("SUAS CONVERSAS")
        conversations_label.setObjectName("sectionLabel")
        side.addWidget(conversations_label)
        self.history_list = QListWidget()
        self.history_list.setObjectName("historyList")
        self.history_list.setSpacing(5)
        self.history_list.itemClicked.connect(lambda item: self._open_chat(item.data(Qt.ItemDataRole.UserRole)))
        side.addWidget(self.history_list, 1)
        self.delete_button = QPushButton("Excluir conversa selecionada")
        self.delete_button.setObjectName("subtleButton")
        self.delete_button.clicked.connect(self._delete_chat)
        side.addWidget(self.delete_button)
        self.export_button = QPushButton("Exportar conversa")
        self.export_button.setObjectName("subtleButton")
        self.export_button.clicked.connect(self._export_chat)
        side.addWidget(self.export_button)

        streak_card = QFrame()
        streak_card.setObjectName("streakCard")
        streak_layout = QVBoxLayout(streak_card)
        streak_layout.setContentsMargins(15, 16, 15, 16)
        streak_layout.setSpacing(6)
        streak_name = QLabel("✦  SUA CONSTÂNCIA")
        streak_name.setObjectName("streakTitle")
        streak_layout.addWidget(streak_name)
        self.streak_value = QLabel()
        self.streak_value.setObjectName("streakValue")
        streak_layout.addWidget(self.streak_value)
        self.streak_subtitle = QLabel()
        self.streak_subtitle.setObjectName("streakSubtitle")
        streak_layout.addWidget(self.streak_subtitle)
        streak_tip = QLabel("Volte amanhã para continuar sua sequência.")
        streak_tip.setObjectName("streakTip")
        streak_tip.setWordWrap(True)
        streak_layout.addWidget(streak_tip)
        side.addWidget(streak_card)
        side_footer = QLabel("PROGRESSO LOCAL  ·  PRIVADO")
        side_footer.setObjectName("sideFooter")
        side_footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        side.addWidget(side_footer)
        outer.addWidget(sidebar)

        # RIGHT: current chat, activity, attachment composer
        main = QFrame()
        main.setObjectName("main")
        area = QVBoxLayout(main)
        area.setContentsMargins(34, 26, 34, 21)
        area.setSpacing(13)
        top = QHBoxLayout()
        header = QVBoxLayout()
        header.setSpacing(5)
        heading = QLabel("Converse. Aprenda. Evolua.")
        heading.setObjectName("heading")
        header.addWidget(heading)
        self.chat_title = QLabel("Uma nova conversa")
        self.chat_title.setObjectName("subtitle")
        header.addWidget(self.chat_title)
        top.addLayout(header)
        top.addStretch()
        self.status = QLabel()
        self.status.setObjectName("status")
        top.addWidget(self.status)
        area.addLayout(top)

        self.chat_scroll = QScrollArea()
        self.chat_scroll.setObjectName("chatScroll")
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.message_area = QWidget()
        self.message_area.setObjectName("messageArea")
        self.message_layout = QVBoxLayout(self.message_area)
        self.message_layout.setContentsMargins(5, 13, 8, 14)
        self.message_layout.setSpacing(15)
        self.message_layout.addStretch()
        self.chat_scroll.setWidget(self.message_area)
        area.addWidget(self.chat_scroll, 1)

        self.transcript = QLabel("Transcrição de voz: —")
        self.transcript.setObjectName("transcript")
        self.transcript.setWordWrap(True)
        self.transcript.hide()
        area.addWidget(self.transcript)

        activity_label = QLabel("ATIVIDADE DO ASSISTENTE")
        activity_label.setObjectName("sectionLabel")
        area.addWidget(activity_label)
        self.progress_box = QPlainTextEdit()
        self.progress_box.setObjectName("progressBox")
        self.progress_box.setReadOnly(True)
        self.progress_box.setMaximumHeight(80)
        self.progress_box.setMinimumHeight(63)
        self.progress_box.setPlaceholderText("As etapas de processamento aparecerão aqui.")
        area.addWidget(self.progress_box)

        self.media_bar = QScrollArea()
        self.media_bar.setObjectName("mediaBar")
        self.media_bar.setWidgetResizable(False)
        self.media_bar.setFrameShape(QFrame.Shape.NoFrame)
        self.media_bar.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.media_bar.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.media_bar.setFixedHeight(51)
        self.media_content = QWidget()
        self.media_content.setObjectName("mediaContent")
        media_line = QHBoxLayout(self.media_content)
        media_line.setContentsMargins(6, 3, 6, 3)
        self.media_line = media_line
        self.media_bar.setWidget(self.media_content)
        self.media_bar.hide()
        area.addWidget(self.media_bar)

        composer = QFrame()
        composer.setObjectName("composer")
        composer_row = QHBoxLayout(composer)
        composer_row.setContentsMargins(9, 7, 9, 7)
        composer_row.setSpacing(8)
        self.attach_button = QPushButton("＋")
        self.attach_button.setObjectName("attachButton")
        self.attach_button.setToolTip("Importar imagens, vídeos ou áudios")
        self.attach_button.setFixedSize(42, 42)
        self.attach_button.clicked.connect(self._attach_files)
        composer_row.addWidget(self.attach_button)
        self.input = QLineEdit()
        self.input.setObjectName("messageInput")
        self.input.setPlaceholderText("Escreva sua mensagem aqui...")
        self.input.returnPressed.connect(self._submit)
        composer_row.addWidget(self.input, 1)
        self.voice_button = QPushButton("◉  Voz")
        self.voice_button.setObjectName("voiceButton")
        self.voice_button.clicked.connect(self._toggle_voice)
        composer_row.addWidget(self.voice_button)
        self.send_button = QPushButton("Enviar  ➜")
        self.send_button.setObjectName("sendButton")
        self.send_button.clicked.connect(lambda _checked: self._submit())
        composer_row.addWidget(self.send_button)
        area.addWidget(composer)
        note = QLabel("Mensagens, imagens e áudios são enviados diretamente ao Gemini. Vídeos ficam no histórico local.")
        note.setObjectName("privacyNote")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.setWordWrap(True)
        area.addWidget(note)
        outer.addWidget(main, 1)

        self.setStyleSheet(STYLES)
        self._refresh_streak()

    def _refresh_streak(self):
        count = int(self.activity.get("current") or 0)
        self.streak_value.setText(f"{count}  {'dia' if count == 1 else 'dias'}  ✦")
        best = int(self.activity.get("best") or 0)
        self.streak_subtitle.setText(f"Recorde: {best}  ·  Dias ativos: {self.activity.get('days_used', 0)}")

    def _refresh_activity(self):
        # A session may cross midnight; record activity on the next interaction as well.
        self.activity = self.storage.record_daily_use()
        self._refresh_streak()

    def _populate_chats(self):
        current = self.active_chat_id
        self.history_list.blockSignals(True)
        self.history_list.clear()
        for chat in self.storage.chats():
            title = chat.get("title", "Nova conversa")
            item = QListWidgetItem("▤   " + title)
            item.setData(Qt.ItemDataRole.UserRole, chat["id"])
            item.setToolTip(title)
            self.history_list.addItem(item)
            if chat["id"] == current:
                self.history_list.setCurrentItem(item)
        self.history_list.blockSignals(False)

    def _open_chat(self, chat_id: str):
        if self.command_worker or self.speech_worker:
            return
        chat = self.storage.get(chat_id)
        if chat is None:
            return
        self._discard_pending()
        self.active_chat_id = chat_id
        self.welcome_widget = None
        while self.message_layout.count() > 1:
            item = self.message_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.chat_title.setText(chat.get("title", "Nova conversa"))
        self.progress_box.clear()
        self.transcript.hide()
        self.assistant.history = []
        self.assistant.last_project = None
        for message in chat["messages"]:
            self._render_message(message["role"], message.get("content", ""), message.get("attachments", []))
            if message["role"] in ("user", "assistant") and (message.get("content") or message.get("attachments")) and message.get("context", True):
                entry = {"role": message["role"], "content": message["content"]}
                if message["role"] == "user":
                    entry["attachments"] = message.get("attachments", [])
                self.assistant.history.append(entry)
        self.assistant.history = self.assistant.history[-12:]
        if not chat["messages"]:
            self._render_welcome()
        self._populate_chats()
        QTimer.singleShot(0, self._scroll_bottom)

    def _render_welcome(self):
        card = QFrame()
        card.setObjectName("welcomeCard")
        card.setMaximumWidth(580)
        col = QVBoxLayout(card)
        col.setContentsMargins(24, 22, 24, 22)
        col.setSpacing(10)
        symbol = QLabel("✧  L.I.N.G.O.")
        symbol.setObjectName("welcomeBrand")
        col.addWidget(symbol)
        title = QLabel("Seu próximo diálogo começa aqui.")
        title.setObjectName("welcomeTitle")
        title.setWordWrap(True)
        col.addWidget(title)
        sub = QLabel("Escreva uma mensagem, grave sua voz ou importe imagens, vídeos e áudios. Suas conversas ficam organizadas no histórico à esquerda.")
        sub.setObjectName("welcomeText")
        sub.setWordWrap(True)
        col.addWidget(sub)
        self.welcome_widget = card
        self.message_layout.insertWidget(0, card, 0, Qt.AlignmentFlag.AlignHCenter)

    def _new_chat(self):
        if self.command_worker or self.speech_worker:
            return
        self._open_chat(self.storage.new_chat()["id"])
        self.input.setFocus()

    def _delete_chat(self):
        if self.command_worker or self.speech_worker or not self.active_chat_id:
            return
        answer = QMessageBox.question(self, "Excluir conversa", "Deseja apagar esta conversa e seus anexos salvos?",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.storage.remove_chat(self.active_chat_id)
        chats = self.storage.chats()
        self._open_chat(chats[0]["id"] if chats else self.storage.new_chat()["id"])

    def _export_chat(self):
        if not self.active_chat_id or self.command_worker or self.speech_worker:
            return
        chat = self.storage.get(self.active_chat_id)
        if chat is None:
            return
        suggested = "LINGO-conversa-" + self.active_chat_id[:8] + ".txt"
        path, _ = QFileDialog.getSaveFileName(self, "Exportar conversa", suggested, "Texto (*.txt)")
        if not path:
            return
        try:
            self.storage.export_chat_text(self.active_chat_id, path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Falha ao exportar", str(exc))
            return
        self._set_status("Conversa exportada")

    def _render_message(self, role: str, content: str, attachments: list[dict]):
        row_widget = QWidget()
        row_widget.setObjectName("messageRow")
        line = QHBoxLayout(row_widget)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(0)
        if role == "user":
            line.addStretch(1)
        bubble = QFrame()
        bubble.setObjectName("userBubble" if role == "user" else "errorBubble" if role == "error" else "assistantBubble")
        bubble.setMaximumWidth(650)
        bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        col = QVBoxLayout(bubble)
        col.setContentsMargins(17, 12, 17, 14)
        col.setSpacing(9)
        role_label = QLabel({"user": "VOCÊ", "assistant": "L.I.N.G.O.", "error": "ATENÇÃO"}.get(role, "L.I.N.G.O."))
        role_label.setObjectName("userRole" if role == "user" else "errorRole" if role == "error" else "assistantRole")
        col.addWidget(role_label)
        if content:
            body = QLabel(content)
            body.setObjectName("messageText")
            body.setWordWrap(True)
            body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            body.setMinimumWidth(170)
            col.addWidget(body)
        for media in attachments:
            path = Path(media.get("path", ""))
            if media.get("kind") == "image" and path.is_file():
                preview = QPixmap(str(path))
                if not preview.isNull():
                    thumb = QLabel()
                    thumb.setPixmap(preview.scaled(236, 138, Qt.AspectRatioMode.KeepAspectRatio,
                                                   Qt.TransformationMode.SmoothTransformation))
                    thumb.setObjectName("thumbnail")
                    col.addWidget(thumb)
            category = {"image": "▧", "audio": "♫", "video": "▶"}.get(media.get("kind"), "▤")
            display = media.get("name", "Arquivo")
            button = QPushButton(f"{category}  {display[:46]}   ↗")
            button.setObjectName("mediaLink")
            button.setToolTip("Abrir arquivo salvo no dispositivo")
            button.clicked.connect(lambda _checked=False, file_path=str(path): self._open_media(file_path))
            col.addWidget(button)
        line.addWidget(bubble)
        if role != "user":
            line.addStretch(1)
        self.message_layout.insertWidget(self.message_layout.count() - 1, row_widget)
        QTimer.singleShot(0, self._scroll_bottom)

    def _open_media(self, path: str):
        target = Path(path)
        try:
            if target.resolve().parent != self.storage.media_dir.resolve() or not target.is_file():
                raise FileNotFoundError("Anexo não encontrado no armazenamento local")
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(target))):
                raise OSError("O Windows não encontrou um aplicativo para abrir este formato")
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível abrir", str(exc))

    def _scroll_bottom(self):
        bar = self.chat_scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _append_chat(self, who: str, text: str, attachments: list[dict] | None = None, *, context: bool = True):
        role = {"Você": "user", "Erro": "error"}.get(who, "assistant")
        if not self.active_chat_id:
            return
        message = self.storage.add_message(self.active_chat_id, role, text, attachments, context=context and role != "error")
        if self.welcome_widget is not None:
            self.message_layout.removeWidget(self.welcome_widget)
            self.welcome_widget.deleteLater()
            self.welcome_widget = None
        self._render_message(role, message["content"], message["attachments"])
        self.chat_title.setText(self.storage.get(self.active_chat_id)["title"])
        self._populate_chats()

    def _attach_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Importar arquivos", "",
            "Mídias (*.png *.jpg *.jpeg *.gif *.webp *.bmp *.mp3 *.wav *.m4a *.aac *.ogg *.flac *.mp4 *.mov *.avi *.mkv *.webm);;"
            "Imagens (*.png *.jpg *.jpeg *.gif *.webp *.bmp);;"
            "Áudios (*.mp3 *.wav *.m4a *.aac *.ogg *.flac);;"
            "Vídeos (*.mp4 *.mov *.avi *.mkv *.webm)",
        )
        errors = []
        for path in paths:
            if len(self.pending_media) >= 6:
                errors.append("Máximo de 6 arquivos por mensagem")
                break
            try:
                self.pending_media.append(self.storage.add_media(path))
            except (ValueError, OSError) as exc:
                errors.append(f"{Path(path).name}: {exc}")
        self._refresh_media_bar()
        if errors:
            QMessageBox.warning(self, "Importação parcial", "\n".join(errors[:6]))

    def _refresh_media_bar(self):
        while self.media_line.count():
            item = self.media_line.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for index, item in enumerate(self.pending_media):
            kind_icon = {"image": "▧", "audio": "♫", "video": "▶"}[item["kind"]]
            chip = QPushButton(f"{kind_icon}  {item['name'][:20]}  ×")
            chip.setObjectName("mediaChip")
            chip.setToolTip("Remover anexo antes do envio")
            chip.clicked.connect(lambda _checked=False, i=index: self._remove_pending(i))
            self.media_line.addWidget(chip)
        self.media_content.adjustSize()
        self.media_bar.setVisible(bool(self.pending_media))

    def _remove_pending(self, index: int):
        if 0 <= index < len(self.pending_media):
            item = self.pending_media.pop(index)
            self.storage.remove_media(item["path"])
            self._refresh_media_bar()

    def _discard_pending(self):
        for attachment in self.pending_media:
            self.storage.remove_media(attachment["path"])
        self.pending_media.clear()
        self._refresh_media_bar()

    def _set_status(self, status: str):
        self.status.setText("●  " + status)

    def _set_busy(self, busy: bool):
        for control in (self.send_button, self.attach_button, self.new_button, self.export_button,
                        self.delete_button, self.history_list, self.input):
            control.setEnabled(not busy)
        # Record button may need to remain active so it can stop recording.
        if self.speech_worker is None:
            self.voice_button.setEnabled(not busy)

    def _progress(self, text: str):
        self.progress_box.appendPlainText("•  " + text)
        if text.startswith(("Executando", "Criando", "Gerando", "Abrindo")):
            self._set_status("Executando")
        elif text.startswith("Ouvindo"):
            self._set_status("Ouvindo")
        elif text.startswith("Enviando áudio"):
            self._set_status("Processando")

    def _submit(self, text: str | None = None):
        if self.command_worker is not None or self.speech_worker is not None:
            return
        command = (text if text is not None else self.input.text()).strip()
        if not command and not self.pending_media:
            self._set_status("Digite uma mensagem")
            return
        self._refresh_activity()
        media = list(self.pending_media)
        self.pending_media.clear()
        self._refresh_media_bar()
        self.input.clear()
        self.progress_box.clear()
        self._append_chat("Você", command, media)
        self._set_busy(True)
        self._set_status("Pensando")
        self.command_worker = CommandWorker(self.assistant, command, media)
        self.command_worker.progress.connect(self._progress)
        self.command_worker.completed.connect(self._command_done)
        self.command_worker.failed.connect(self._command_failed)
        self.command_worker.start()

    def _command_done(self, result: dict):
        self._append_chat("L.I.N.G.O.", result["answer"])
        for action in result.get("actions", []):
            data = action["result"]
            if "error" in data:
                self._append_chat("Erro", data["error"])
            elif action["tool"] == "create_python_project":
                receipt = (f"Pasta: {data['path']}\nArquivos: {', '.join(data['files_created']) or 'nenhum'}\n"
                           f".venv: {'criado' if data['venv_created'] else 'não criado'}\n"
                           f"VS Code: {'comando aceito' if data['vscode_opened'] else 'não aberto'}")
                if data["errors"]:
                    receipt += "\nPendências: " + "; ".join(data["errors"])
                self._append_chat("L.I.N.G.O.", receipt, context=False)
            elif action["tool"] == "open_project":
                self._append_chat("L.I.N.G.O.", f"Pasta: {data['path']}\nVS Code: {'comando aceito' if data['vscode_opened'] else data['error']}", context=False)
        self._progress("Concluído")
        self._finish_command()

    def _command_failed(self, error: str):
        self._append_chat("Erro", error)
        self._set_status("Erro")
        self._finish_command(reset_status=False)

    def _finish_command(self, reset_status: bool = True):
        if self.command_worker is not None:
            self.command_worker.wait(1000)
        self.command_worker = None
        self._set_busy(False)
        self.voice_button.setEnabled(True)
        self.input.setFocus()
        if reset_status:
            self._set_status("Disponível")

    def _toggle_voice(self):
        if self.speech_worker is not None:
            self.speech_worker.request_stop()
            self.voice_button.setEnabled(False)
            self._set_status("Processando áudio")
            return
        if self.command_worker is not None:
            return
        key = os.getenv("GEMINI_API_KEY", "")
        if not key:
            self._append_chat("Erro", "GEMINI_API_KEY ausente. Configure uma chave do Google AI Studio no arquivo .env.")
            return
        self._refresh_activity()
        self.progress_box.clear()
        self.speech_worker = SpeechWorker(key)
        self.speech_worker.progress.connect(self._progress)
        self.speech_worker.completed.connect(self._speech_done)
        self.speech_worker.failed.connect(self._speech_failed)
        self.speech_worker.start()
        self._set_busy(True)
        self.voice_button.setEnabled(True)
        self.voice_button.setText("■  Parar")
        self._set_status("Ouvindo")

    def _speech_done(self, transcript: str):
        self.transcript.setText("Transcrição de voz: " + transcript)
        self.transcript.show()
        self._finish_speech()
        self._submit(transcript)

    def _speech_failed(self, error: str):
        self._append_chat("Erro", error)
        self._finish_speech()
        self._set_status("Erro")

    def _finish_speech(self):
        if self.speech_worker is not None:
            self.speech_worker.wait(1000)
        self.speech_worker = None
        self.voice_button.setText("◉  Voz")
        self.voice_button.setEnabled(True)
        self._set_busy(False)

    def closeEvent(self, event):
        if self.speech_worker is not None or self.command_worker is not None:
            if self.speech_worker is not None:
                self.speech_worker.request_stop()
            self._set_status("Aguarde a operação terminar")
            event.ignore()
            return
        self._discard_pending()
        super().closeEvent(event)


def run_app(root: Path):
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("L.I.N.G.O.")
    try:
        window = MainWindow(root)
    except Exception as exc:
        QMessageBox.critical(None, "L.I.N.G.O. — erro ao iniciar", str(exc))
        return 1
    window.show()
    return app.exec()


STYLES = """
QWidget { background: #0B101B; color: #E7ECF7; font-family: 'Segoe UI'; font-size: 13px; }
QWidget#root { background: #0B101B; }
QFrame#sidebar { background: #101727; border-right: 1px solid #252F44; }
QLabel#logo { background: #18B8B1; color: #061822; font-size: 26px; font-weight: 800; border-radius: 13px; }
QLabel#brand { color: #F4F8FF; font-size: 19px; font-weight: 800; letter-spacing: 2px; }
QLabel#brandCaption { color: #6F829C; font-size: 9px; font-weight: 700; letter-spacing: 1.2px; }
QLabel#sectionLabel { color: #8192B1; font-size: 10px; font-weight: 800; letter-spacing: 1.7px; }
QPushButton { background: #26344D; color: #DEE8F5; border: 1px solid #354663; border-radius: 10px; padding: 9px 13px; font-weight: 600; }
QPushButton:hover { background: #344760; border-color: #508B9D; }
QPushButton:pressed { background: #20465A; }
QPushButton:disabled { color: #66768C; background: #1B2638; border-color: #26344A; }
QPushButton#newChatButton { background: #182B3E; border: 1px solid #266A73; color: #84E7DF; text-align: left; font-size: 13px; font-weight: 700; }
QPushButton#newChatButton:hover { background: #1D3E50; }
QPushButton#subtleButton { background: transparent; border: 0; color: #71839F; text-align: left; padding-left: 10px; }
QPushButton#subtleButton:hover { color: #EFACAB; background: #2A2634; }
QListWidget#historyList { background: transparent; border: 0; outline: none; color: #B7C6DB; }
QListWidget#historyList::item { background: transparent; border-radius: 9px; padding: 11px 7px; margin: 1px 1px; }
QListWidget#historyList::item:hover { background: #1F2D44; }
QListWidget#historyList::item:selected { background: #203A49; color: #D3FFFA; }
QFrame#streakCard { background: #182437; border: 1px solid #344456; border-radius: 16px; }
QLabel#streakTitle { background: transparent; color: #97C7C8; font-size: 10px; font-weight: 800; letter-spacing: 1px; }
QLabel#streakValue { background: transparent; color: #F3F8FF; font-size: 27px; font-weight: 800; }
QLabel#streakSubtitle { background: transparent; color: #91A4BB; font-size: 11px; }
QLabel#streakTip { background: transparent; color: #7590AC; font-size: 11px; }
QLabel#sideFooter { color: #596B83; font-size: 9px; letter-spacing: 1px; }
QFrame#main { background: #0B101B; }
QLabel#heading { color: #F1F6FF; font-size: 23px; font-weight: 800; }
QLabel#subtitle { color: #8499B4; font-size: 12px; }
QLabel#status { background: #162A32; color: #79D6C4; border: 1px solid #2B5658; border-radius: 12px; padding: 8px 12px; font-size: 11px; font-weight: 700; }
QScrollArea#chatScroll, QWidget#messageArea { background: transparent; border: none; }
QWidget#messageRow { background: transparent; }
QFrame#userBubble { background: #1A3646; border: 1px solid #275469; border-radius: 16px; }
QFrame#assistantBubble { background: #192236; border: 1px solid #2D3A56; border-radius: 16px; }
QFrame#errorBubble { background: #40262A; border: 1px solid #74434B; border-radius: 16px; }
QLabel#userRole { background: transparent; color: #83E8E2; font-size: 10px; font-weight: 800; letter-spacing: 1px; }
QLabel#assistantRole { background: transparent; color: #C0B0FF; font-size: 10px; font-weight: 800; letter-spacing: 1px; }
QLabel#errorRole { background: transparent; color: #FFC2B8; font-size: 10px; font-weight: 800; }
QLabel#messageText { background: transparent; color: #EDF2FF; font-size: 13px; line-height: 1.5; }
QLabel#thumbnail { background: transparent; }
QPushButton#mediaLink { background: #27374B; border: 1px solid #3B4D63; color: #BFE9E7; text-align: left; padding: 8px; }
QFrame#welcomeCard { background: #121E2F; border: 1px solid #2D415B; border-radius: 20px; }
QLabel#welcomeBrand { background: transparent; color: #6DD9D0; font-size: 15px; font-weight: 800; letter-spacing: 1px; }
QLabel#welcomeTitle { background: transparent; color: #F3F6FF; font-size: 20px; font-weight: 800; }
QLabel#welcomeText { background: transparent; color: #9AAEC7; font-size: 13px; }
QPlainTextEdit#progressBox { background: #111A2A; color: #9BB4CA; border: 1px solid #25344B; border-radius: 10px; padding: 9px 10px; font-size: 11px; }
QFrame#composer { background: #161F30; border: 1px solid #384A62; border-radius: 16px; }
QLineEdit#messageInput { background: transparent; border: none; padding: 10px 4px; selection-background-color: #147D86; font-size: 13px; }
QPushButton#attachButton { background: #25324A; border: 0; border-radius: 10px; font-size: 25px; padding: 0; }
QPushButton#voiceButton { background: #29344A; color: #D4DDF1; border: none; padding: 12px 13px; }
QPushButton#sendButton { background: #1BB5AA; border: none; color: #05222D; padding: 12px 20px; font-weight: 800; }
QPushButton#sendButton:hover { background: #54E1D5; }
QLabel#privacyNote { color: #64768E; font-size: 10px; }
QLabel#transcript { background: #11283A; border-left: 3px solid #39B3BA; border-radius: 5px; padding: 10px; color: #A5D6E0; }
QScrollArea#mediaBar, QWidget#mediaContent { background: transparent; border: 0; }
QPushButton#mediaChip { background: #223348; border: 1px solid #476579; border-radius: 14px; color: #BCE7E6; padding: 7px 9px; font-size: 11px; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: #34485E; border-radius: 4px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""
