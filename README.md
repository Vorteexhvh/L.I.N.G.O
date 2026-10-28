# L.I.N.G.O.

**Language Intelligence & Natural Guidance Operator** — aplicativo de desktop para Windows, com interface moderna, conversas organizadas e sequência diária (*streak*).

A aplicação usa a **API oficial do Google Gemini**, diretamente em `generativelanguage.googleapis.com`, para texto, imagens, áudios e transcrição do microfone. O modelo padrão é `gemini-3.5-flash`, configurável por `GEMINI_MODEL`. O assistente mantém as ferramentas de desenvolvimento de projetos Python e pode oferecer explicações sobre idiomas. Vídeos importados permanecem disponíveis no histórico local, mas seu conteúdo não é enviado para análise.

## Instalação no Windows

1. Instale **Python 3.10 ou superior** e abra o PowerShell na pasta do aplicativo.
2. Execute estes comandos:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

3. Obtenha uma chave no [Google AI Studio](https://aistudio.google.com/apikey) e configure `.env`:

```dotenv
GEMINI_API_KEY=sua_chave_do_google_ai_studio
GEMINI_MODEL=gemini-3.5-flash
WORKSPACE_ROOT=workspace
```

Mantenha esse arquivo privado. Se aparecer erro de chave inválida ou sem permissão, confira `GEMINI_API_KEY` e as permissões da chave no Google AI Studio. O uso depende da disponibilidade do modelo e da cota da sua conta Google.

Falhas temporárias HTTP 500, 502, 503 e 504 são repetidas automaticamente até três tentativas, com espera crescente. Se persistirem, a interface informa a indisponibilidade sem repetir as ações locais em projetos.
4. Execute o aplicativo:

```powershell
.\.venv\Scripts\python.exe main.py
```

Depois de instalar, use **Iniciar LINGO.cmd** para abrir sem console, caso o Windows permita a execução do iniciador. Se o Controle Inteligente de Aplicativos/Smart App Control bloquear o pacote, não desative proteções: execute pelo Python instalado ou utilize um instalador com assinatura digital confiável.

## Novas funções

- **Barra lateral:** botão de nova conversa e histórico por título; clique em qualquer conversa para restaurá-la. O contexto recente da conversa selecionada é restaurado para a IA.
- **Persistência:** histórico guardado localmente no perfil do usuário em `%LOCALAPPDATA%\LINGO\history.json` no Windows. As conversas sobrevivem ao fechamento e à reabertura.
- **Exportação:** clique em **Exportar conversa** para salvar a conversa selecionada como texto UTF-8, incluindo mensagens, horários e nomes dos anexos.
- **Importar:** clique no **+** ao lado da caixa de mensagem para importar até 6 imagens (`png`, `jpg`, `jpeg`, `gif`, `webp`, `bmp`), áudios (`wav`, `mp3`, `m4a`, `aac`, `ogg`, `flac`) ou vídeos (`mp4`, `mov`, `avi`, `mkv`, `webm`) por mensagem. Os arquivos são copiados para `%LOCALAPPDATA%\LINGO\media`, são exibidos na conversa e podem ser abertos com o aplicativo padrão do Windows. Imagens e áudios são enviados ao Gemini junto com a mensagem e ficam disponíveis no contexto recente da conversa. O envio de imagens e áudios tem limite combinado de 35 MB por mensagem. Vídeos ficam apenas no histórico local. Limites por arquivo: imagem 15 MB, áudio 35 MB, vídeo 150 MB.
- **Streak:** conta um dia ativo quando o aplicativo é aberto ou usado nesse dia (uma vez por data local). Dias consecutivos aumentam a sequência; perder um dia reinicia a sequência. O recorde e os dias totais ficam registrados.
- **Exclusão:** o botão de excluir pede confirmação e remove do armazenamento a conversa e suas cópias de mídia.

**Privacidade:** o histórico e as cópias dos anexos ficam no dispositivo. Mensagens, imagens e áudios incluídos no contexto, além da gravação de voz, são transmitidos diretamente à API do Google Gemini. Vídeos locais não são enviados. Cobrança e limites seguem a configuração da sua conta Google.

## Funcionalidades preservadas

O arquivo `.env` define `WORKSPACE_ROOT` (a pasta segura para ações em projetos). Os comandos originais para listar, criar, abrir e inspecionar projetos Python continuam disponíveis, bem como a gravação/transcrição pelo microfone. Para iniciar uma conversa comum, digite uma pergunta como "Quero praticar inglês: corrija minhas frases". O uso da IA exige internet, chave Gemini válida e cota disponível. A transcrição usa o mesmo modelo e a mesma chave das conversas.

A pasta interna `jarvis_dev` continua com o mesmo nome por compatibilidade com o código-base e com os testes existentes; o nome exibido do produto é **L.I.N.G.O.**.

## Testes

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Dados do histórico não são salvos na pasta dos projetos; são gravados no perfil local do usuário.
