# Postman Pro setup for Avito OAuth Helper

This guide explains how to import and use the enhanced Postman collection and environment with **firewall detection**, **proxy rotation**, and **Messages API** support for the Avito API.

## New Features

- **🛡️ Firewall Detection**: Automatic detection of IP blocking with retry logic
- **🔄 Proxy Rotation**: Support for proxy lists and automatic rotation on blocks  
- **💬 Messages API**: Complete set of requests for chat/messaging functionality
- **⚡ Enhanced OAuth**: Improved error handling and debugging

Files included

- `postman_avito_collection.json` — Enhanced Postman Collection with firewall bypass
- `postman_avito_environment.json` — Pro Environment with 35+ variables for advanced features

## Quick Setup

1. **Import files**: Postman → Import → File → choose both JSON files
2. **Select environment**: Top-right dropdown → `Avito OAuth Env Pro`
3. **Fill credentials**: Set `client_id`, `client_secret` in environment variables

## Basic OAuth Flow (No IP Issues)

1. **Check IP status first**: Run `Check Firewall Status` → should show "✅ IP is not blocked"
2. **Generate auth URL**: Run `Build Authorization URL` → copy `auth_url_built` from Console
3. **Get authorization code**: Open URL in browser → complete login → copy `code` from redirect
4. **Exchange for tokens**: Set `code` in environment → Run `Exchange Authorization Code (token)`
5. **Success**: Check `access_token` and `refresh_token` in environment

## Firewall Bypass (IP Blocked)

If `Check Firewall Status` shows "❌ IP is blocked":

### Option 1: Enable Auto Proxy Rotation
```javascript
// Set in environment:
firewall_bypass_enabled = "true"
auto_proxy_rotation = "true"  
proxy_list = "proxy1:port,proxy2:port,proxy3:port"
max_proxy_retries = "5"
```

### Option 2: Manual IP Change
- Use VPN/mobile hotspot
- Restart router (30 sec disconnect)
- Use different network

### Option 3: Browser Captcha Solve
- Open `https://avito.ru` in browser
- Solve captcha if presented  
- Return to Postman immediately after clearance

## Messages API Usage

After successful OAuth, you can use the Messages API:

### 1. Get Account ID
```
GET /messenger/v1/accounts/{{account_id}}
```
Set your `account_id` in environment first.

### 2. List Your Chats  
```
GET /messenger/v1/accounts/{{account_id}}/chats
```
Adjust `chat_limit` and `chat_offset` as needed.

### 3. Get Messages from Chat
```
GET /messenger/v1/accounts/{{account_id}}/chats/{{chat_id}}/messages  
```
Set `chat_id` from previous response, adjust `message_limit`/`message_offset`.

### 4. Send Message
```
POST /messenger/v1/accounts/{{account_id}}/chats/{{chat_id}}/messages
```
Set `message_text` in environment (default: "Hello from Postman!").

## Environment Variables Reference

### OAuth & Authentication
- `client_id`, `client_secret` — Your app credentials
- `redirect_uri` — Registered callback (default: Postman's)
- `access_token`, `refresh_token` — Obtained tokens
- `auth_url`, `token_url` — OAuth endpoints

### Firewall & Proxy Management  
- `firewall_bypass_enabled` — Enable proxy features ("true"/"false")
- `auto_proxy_rotation` — Auto-switch on blocks ("true"/"false")
- `proxy_list` — Comma-separated proxy list "host1:port1,host2:port2"
- `current_proxy_index` — Current proxy position (auto-managed)
- `max_proxy_retries` — Max attempts before giving up
- `firewall_status` — Current IP status ("blocked"/"clear")

### Messages API
- `account_id` — Your Avito account ID
- `chat_id` — Target chat ID for messages
- `chat_limit`, `chat_offset` — Pagination for chats list
- `message_limit`, `message_offset` — Pagination for messages
- `message_text` — Text to send in new messages

### Debug & Status
- `firewall_detected` — Set when blocking detected
- `last_token_response` — Last raw token response for debugging
- `oauth_success` — Set to "true" on successful token exchange
- `retry_exhausted` — Set when max retries reached

## Troubleshooting

### Common Issues

**"❌ IP is blocked by Avito firewall"**
- Enable proxy rotation OR change IP/VPN OR solve browser captcha

**"invalid_grant" in token exchange**  
- Check `redirect_uri` matches exactly what's registered
- Get fresh `code` (codes expire in ~10 minutes)  
- Verify `client_id`/`client_secret` are correct

**Messages API returns 403/401**
- Check `access_token` is valid and not expired
- Verify scopes include `messages.read` and/or `messages.write`  
- Confirm `account_id` is correct

**Proxy rotation not working**
- Set `firewall_bypass_enabled = "true"`
- Format `proxy_list` as: `"proxy1.com:8080,proxy2.com:3128"`
- Check proxy credentials if required

### Debug Tips

1. **Always run `Check Firewall Status` first** before OAuth
2. **Monitor Postman Console** for detailed logs and error messages
3. **Check environment variables** after each request for auto-set values
4. **Use `last_token_response`** to see raw responses when debugging failures

### Manual Commands (Alternative)

If Postman issues persist, use the Python script:
```powershell
# Quick auth URL generation  
python .\tools\get_personal_token.py --client-id $env:AVITO_CLIENT_ID --client-secret $env:AVITO_CLIENT_SECRET --redirect-uri https://oauth.pstmn.io/v1/callback --print-only

# Full OAuth with debug
python .\tools\get_personal_token.py --client-id $env:AVITO_CLIENT_ID --client-secret $env:AVITO_CLIENT_SECRET --redirect-uri https://oauth.pstmn.io/v1/callback --no-browser --debug
```

## Security Notes

- **Never share** `client_secret`, `access_token`, or `refresh_token` publicly
- **Mask secrets** when sharing debug info: replace with `REDACTED`  
- **Use HTTPS-only** redirect URIs in production
- **Rotate tokens** regularly and revoke unused ones

## Support

If you encounter issues:
1. Check `last_token_response` for detailed error messages
2. Verify environment variables are set correctly  
3. Try manual IP change/VPN if firewall blocks persist
4. Share **masked** debug info (replace secrets with `REDACTED`)

