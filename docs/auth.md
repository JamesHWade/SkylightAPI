# Authentication Guide (How to Capture Your Token)

> **Unofficial reference** — Use only with accounts you own or are authorized to use. Never commit real tokens.

Skylight requests observed so far use either:
- `Authorization: Basic <opaque token>` — **Not** username:password; an opaque bearer-like token.
- `Authorization: Bearer <jwt>` — Standard bearer token (likely JWT).

This guide shows how to capture a token safely for testing documented endpoints.

---

## 1) Programmatic Authentication (API Login)

If you need to authenticate programmatically (for scripts, automation, or testing), you can use the login endpoint to obtain a token.

### Endpoint

```http
POST https://app.ourskylight.com/api/sessions
Content-Type: application/json
```

### Request Body

```json
{
  "email": "yourname@email.com",
  "password": "thisis-yourpa-ssword"
}
```

### Response

```json
{
  "data": {
    "id": "12345678",
    "type": "authenticated_user",
    "attributes": {
      "email": "yourname@email.com",
      "token": "atu_Gxf2DRxSWCC2WIN8tvj7xDdA5h5ITt6a",
      "subscription_status": "basic"
    }
  },
  "meta": {
    "password_reset": true
  }
}
```

> **Note**: The above example uses fictional credentials for demonstration purposes only. Real tokens and IDs will differ. Never commit real credentials to version control.

### Generating Your Authorization Token

To use this token in subsequent API requests, you need to:

1. **Concatenate** the `id` and `token` fields with a colon separator:
   ```
   12345678:atu_Gxf2DRxSWCC2WIN8tvj7xDdA5h5ITt6a
   ```

2. **Base64 encode** the concatenated string:
   ```bash
   echo -n "12345678:atu_Gxf2DRxSWCC2WIN8tvj7xDdA5h5ITt6a" | base64
   ```
   This produces: `MTIzNDU2Nzg6YXR1X0d4ZjJEUnhTV0NDMldJTjh0dmo3eERkQTVoNUlUdDZh`

3. **Use it** in your requests with the `Basic` authorization scheme:
   ```http
   Authorization: Basic MTIzNDU2Nzg6YXR1X0d4ZjJEUnhTV0NDMldJTjh0dmo3eERkQTVoNUlUdDZh
   ```

#### Testing the Base64 Encoding

To verify you're encoding correctly, try this test example:

```bash
# Test with id="testuser123" and token="test_token_abc"
echo -n "testuser123:test_token_abc" | base64
# Expected output: dGVzdHVzZXIxMjM6dGVzdF90b2tlbl9hYmM=
```

If your output matches, you're encoding correctly. Replace with your actual `id:token` from the login response.

### Example (cURL)

```bash
# Login and get token
curl -X POST 'https://app.ourskylight.com/api/sessions' \
  -H 'Content-Type: application/json' \
  -d '{
    "email": "yourname@email.com",
    "password": "thisis-yourpa-ssword"
  }'

# Use the token (after base64 encoding id:token)
curl 'https://app.ourskylight.com/api/frames/REDACTED/chores' \
  -H 'Authorization: Basic REDACTED'
```

### Security Notes

- **Never** commit credentials or real tokens to version control
- Store credentials securely (environment variables, credential managers, etc.)
- The `password_reset` flag in the meta field indicates whether a password reset is required
- Treat the token as a secret — it provides full access to your account

---

## 2) Capture via Proxy (Alternative Method)

Use one of these HTTPS debugging proxies:
- **Proxyman** (macOS GUI)
- **Charles Proxy** (macOS/Windows GUI)
- **mitmproxy** (CLI; scriptable)

### Steps
1. **Install and trust** the proxy's root certificate (System Keychain).
2. Enable **SSL Proxying** / **HTTPS capture**.
3. Launch the Skylight app and **log in**.
4. In the proxy session list, find the first authenticated request (e.g., `GET /api/frames/{frameId}/chores`).
5. Copy the **Authorization** header value.

> Tip: If you only see `CONNECT` entries or 4xx errors, enable SSL for the specific hostname and try again.

### Safety
- Tokens are secrets. **Do not** commit real values.
- When sharing examples, replace with `REDACTED` and keep the structure (header name/value format).

---

## 3) Electron/Chromium Apps (DevTools)

If the desktop app is Electron/Chromium-based:

1. Try **View → Toggle Developer Tools** from the app menu, or launch with:
   ```bash
   open -na "/Applications/Skylight.app" --args --remote-debugging-port=9222
   ```
2. Open Chrome → `chrome://inspect` → **inspect** the Skylight target.
3. Go to **Network** tab → click an API call → **Headers** → copy `Authorization`.

This avoids TLS interception and certificate pinning issues.

---

## 4) If HTTPS Decryption Fails (Certificate Pinning)

Some apps validate the server certificate in code (“pinning”). If your proxy shows CONNECT tunnels but no decrypted traffic:

- Try a different proxy (Proxyman/Charles/mitmproxy).
- Use **Frida** to hook common pinning points (`SecTrustEvaluate`, `NSURLSession`, Alamofire) on macOS.
- Run Skylight in a **VM** or use **transparent proxying** (e.g., mitmproxy as gateway) to redirect traffic.

> **Note**: Respect the app’s ToS and local laws. Use these techniques only for legitimate interoperability/debugging.

---

## 5) Using the Token (Postman/Insomnia/cURL)

- Add the header to your request:
  ```http
  Authorization: Basic REDACTED
  ```
  **or**
  ```http
  Authorization: Bearer REDACTED
  ```

- Example cURL:
  ```bash
  curl 'https://app.ourskylight.com/api/frames/REDACTED/chores?after=2025-08-25&before=2025-08-29'     -H 'Authorization: Basic REDACTED'     -H 'Accept: application/json'
  ```

If you receive **401 Unauthorized**:
- Log out/in in the Skylight app and recapture a fresh token.
- Ensure you copied the header **exactly** (no whitespace changes).

---

## 6) Redaction & Sharing

When contributing examples to this repo:
- Replace tokens and any PII with `REDACTED` (keep keys/shape intact).
- Use stable placeholders for related IDs if structure matters (e.g., `"CATEGORY_REDACTED"`).

See also: `../SECURITY.md` and `../CONTRIBUTING.md`.