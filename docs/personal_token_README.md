Personal token (Authorization Code) helper

This project includes `tools/get_personal_token.py` to guide obtaining a personal Avito access token via Authorization Code flow.

Preconditions
- You need a registered personal application with `client_id` and `client_secret`.
- The app must accept a `redirect_uri` on `http://127.0.0.1:<port>/callback`.

How it works
1. Run the script with your `client_id` and `client_secret`:
   ```powershell
   .\.venv\Scripts\python.exe tools\get_personal_token.py --client-id <ID> --client-secret <SECRET> --redirect-port 8765
   ```
2. The script opens a browser window to Avito's authorization page. Approve the app.
3. The browser will redirect to `http://127.0.0.1:8765/callback` with a code; the script listens and captures it.
4. The script exchanges the code for tokens and saves them to `secrets/personal_token.json`.

Afterwards
- Set `AVITO_PERSONAL_TOKEN` to the `access_token` value or pass `--personal-token` to `resume_messages_downloader.py`.
- The saved `secrets/personal_token.json` will contain `refresh_token` and other fields; you can implement refresh logic as needed.

Security
- Do not commit `secrets/personal_token.json` to version control.
