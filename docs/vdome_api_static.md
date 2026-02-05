# Vdome API static map (APK 2.12.0)

Analysis date: 2026-02-03
Source: decompiled app under vdome/
App: applicationId ru.mts.vdome.resident, versionName 2.12.0, versionCode 200100009
Status: static analysis only (no live traffic capture yet).

## Inventory
- Decompiled sources: vdome/app/src/main/...
- Build metadata: vdome/app/build.gradle, vdome/app/src/main/AndroidManifest.xml
- Config assets: vdome/app/src/main/assets/config/config.json

## Base URLs and environments
- https://gateway.vdome.mts.ru/ (ResidentModule RemoteConfig for intercom and calls)
- https://resident-rest.vdome.mts.ru (ContactsProvider and resident REST)
- https://freecom-app.mts.ru (assets/config/config.json, production host)
- https://kolya.site-stage.freecom-app-test.mts.ru (assets/config/config.json, dev host)

## Common headers (RestApiHeaderInterceptor)
- X-Device-Type: ANDROID
- Request-Id: <uuid>
- X-Device-Token: <firebase installation id> (optional)
- Authorization: Bearer <access_token> (when authenticated)
- X-Auth-Token: <access_token> (when authenticated)

User-Agent in the app is OkHttp; the Python tools default to "okhttp/4.12.0".

## Phone format (static)
- UI formatter expects 10 digits and renders +7 XXX XXX-XX-XX.
- MAX_DIGITS_IN_PHONE_NUMBER is 10 (AddUserFeature).

## Auth flow (static)
1) POST /user-service/api/v2/auth/init
   - Request: AuthorizationQuery {phone}
   - Response: CommonResponse<AuthorizationAnswer>
     - status (string)
     - canSkipSms (bool)
     - refreshToken (ExtRefreshToken {token, expiredAt, timeZone})
2) POST /user-service/api/v2/auth/login
   - Request: VerifyCodeQuery {phone, code}
   - Response: CommonResponse<VerifyCodeAnswer> {accessToken, refreshToken}
3) PUT /user-service/api/v2/auth/refresh
   - Request: RefreshTokensRequest {refreshToken}
   - Response: CommonResponse<String> (access token) OR RefreshAccessTokenResponse
     {accessToken, refreshToken} (AuthApiGateway)
4) POST /user-service/api/v2/auth/logout
   - Request: LogoutQuery {refreshToken}

## Alternative SMS token flow (gw-intercom)
- POST /gw-intercom/token/v1/tokens
  - Request: SendSms {target, transport="sms", type="verifyPhone"}
  - Response: SendSmsResponse {list:[{id}], error?, metadata?}
- PUT /gw-intercom/token/v1/tokens/{modelId}
  - Request: ConfirmSms {id?, code?}
  - Response: not specified in interface (Object)

## Camera preview
- GET https://{api}/api/v2/cameras/{camid}/preview/
  - Header: Authorization: Acc <watch_token>
  - watch_token is returned in camera list responses.

## Endpoint map (static)

### Host: https://resident-rest.vdome.mts.ru

| Method | Path | Request model | Response model | Notes |
| --- | --- | --- | --- | --- |
| POST | /user-service/api/v2/auth/init | AuthorizationQuery {phone} | CommonResponse<AuthorizationAnswer> | X-Device-Type, Request-Id, optional X-Device-Token |
| POST | /user-service/api/v2/auth/login | VerifyCodeQuery {phone, code} | CommonResponse<VerifyCodeAnswer> | X-Device-Type, Request-Id, optional X-Device-Token |
| PUT | /user-service/api/v2/auth/refresh | RefreshTokensRequest {refreshToken} | CommonResponse<String> OR RefreshAccessTokenResponse | X-Device-Type, Request-Id, optional X-Device-Token |
| POST | /user-service/api/v2/auth/logout | LogoutQuery {refreshToken} | Response<Unit> | X-Device-Type, Request-Id, optional X-Device-Token |
| GET | /config | none | List<ConfigVersionItem> | AuthApiGateway |
| GET | /feature | none | List<FeatureToggleItem> | AuthApiGateway |
| PUT | /user-service/api/auth/websso/refresh | none | IdToken | RestApiPaths.PUT_SSO_ID_TOKEN |
| POST | /key-service/master/key/v1/gen | MasterData + header consumerId | MasterDataResponse | consumerId defaults to BuildConfig.SSO_AUTH_CLIENT |

### Host: https://gateway.vdome.mts.ru

| Method | Path | Request model | Response model | Notes |
| --- | --- | --- | --- | --- |
| GET | /domofon/api/intercom/v1/cameras?limit=1000 | none | CameraListResponse | access token headers required; response list uses key "list" |
| GET | /domofon/api/intercom/v2/intercoms?limit=1000&category=intercom | none | IntercomListResponse | access token headers |
| GET | /domofon/api/intercom/v2/intercoms?limit=1000&category=barrier | none | IntercomListResponse | access token headers |
| GET | /domofon/api/intercom/v2/intercoms | none | Object | used as test endpoint in IntercomRestApi |
| POST | /domofon/api/intercom/v2/intercoms/{intercomId}/lock | ActionOpen | Response<Object> | access token headers |
| POST | /domofon/api/intercom/v2/intercoms/{intercomId}/lock/{lockNumber} | ActionOpen | Response<Object> | access token headers |
| GET | /domofon/api/security/v1/users/self | none | UserResponse | access token headers |
| GET | /domofon/api/security/v1/users | none | UserResponse | access token headers |
| POST | /domofon/api/security/v1/users/{userId}/link | AddIntercom | Object | access token headers |
| DELETE | /domofon/api/security/v1/users/{userId} | none | Response<Unit> | access token headers |
| PUT | /domofon/api/security/v1/users/{userId} | RegisterFcmDeviceTokenRequest | Unit | access token headers |
| GET | /gw-intercom/apartment/v1/apartments | none | Apartments | access token headers |
| GET | /gw-intercom/apartment/v1/apartments/{id} | none | Apartments | access token headers |
| POST | /gw-intercom/apartment/v1/apartments/{apartmentId}/block/{userId} | none | Apartments | access token headers |
| DELETE | /gw-intercom/apartment/v1/apartments/{apartmentId}/block/{userId} | none | Apartments | access token headers |
| DELETE | /gw-intercom/apartment/v1/apartments/{apartments}/tenants/{tenants} | body (none) | ResponseRegisterChild | access token headers |
| GET | /gw-intercom/billing/v2/users/{userId}/services | none | BillingListResponse | access token headers |
| GET | /gw-intercom/company/v1/companies/{id} | none | DescriptionResponse | access token headers |
| POST | /gw-intercom/feedback/v1/messages/intercom/{id} | Feedback | Response<Unit> | access token headers |
| POST | /gw-intercom/token/v1/tokens | SendSms | SendSmsResponse | access token headers likely |
| PUT | /gw-intercom/token/v1/tokens/{modelId} | ConfirmSms | Object | access token headers likely |
| POST | /meter-manager/metric/v1/devices | list + query params | List<NewCounters> | query: from, to, size, sort |
| POST | /meter-manager/device/v1/flats | list | CountersDevice | access token headers |
| POST | /payment-service/api/v2/payment/session | RequestPaySession | PaySession | access token headers |
| POST | /user-service/v2/api/auth/logout | LogoutQuery | Response<Unit> | access token headers |
| DELETE | /vdome-smart-facade/api/v1/event | DeleteAllEvents | Response<Unit> | access token headers |

## Security controls (static)
- No explicit certificate pinning, root detection, or SafetyNet/Play Integrity checks found
  in the decompiled app code. OkHttp uses default CertificatePinner.

## Gaps / next steps for dynamic verification
- Capture live auth and intercom traffic with a proxy to confirm payload shapes and
  header requirements.
- Validate refresh response shape (string vs object).
- Save sanitized HTTP samples with timestamps.
