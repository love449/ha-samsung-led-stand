# 삼성 스마트싱스 LED 스탠드 (로컬) – Home Assistant 연동

삼성 스마트싱스 **LED 스탠드**(Wi-Fi 직결, "Works with SmartThings" 계열)를
**SmartThings 클라우드/API 없이** 같은 네트워크 안에서 직접 제어하는 HACS 커스텀 연동입니다.
스마트싱스 API 유료화와 상관없이 계속 동작합니다.

> 개인 환경(모델 IoT-MT428D21K)에서 확인한 방식으로 만들었습니다.
> 같은 계열 기기에서 동작할 가능성이 높지만 모든 모델을 보장하지는 않습니다.

## 기능

| 엔티티 | 설명 |
|---|---|
| `light` | 켜기/끄기, 밝기(1~100%) |
| `select` (조명 모드) | 학습(언어) · 학습(수리) · 학습(멀티미디어) · 야간 · 수면 |

- 기기에서 직접 터치로 바꾼 상태도 10초 안에 HA에 반영됩니다.
- 색온도는 이 스탠드에 없는 기능이라 제공하지 않습니다(색은 조명 모드로 바뀝니다).
- 앱의 타이머/수면 조명 토글은 아직 지원하지 않습니다.

## 설치 (HACS)

1. HACS → 우측 상단 ⋮ → **사용자 지정 저장소**
2. 저장소 주소 입력: `https://github.com/love449/ha-samsung-led-stand`, 유형 **Integration**
3. **Samsung SmartThings LED Stand (Local)** 설치 → **Home Assistant 재시작**

## 기기 등록 (IP만 입력)

1. 설정 → 기기 및 서비스 → **통합 구성요소 추가** → *Samsung SmartThings LED Stand* 검색
2. 스탠드의 **IP 주소**만 입력하면 등록됩니다.
3. 이름이 `SmartLEDStand`로 보이는 기기는 DHCP 자동 발견으로 "발견됨" 카드가 뜨기도 합니다.
4. 이름/영역(예: 다락방)은 HA에서 자유롭게 바꾸세요.

IP가 바뀌면 설정 → 기기 및 서비스 → 해당 항목 ⋮ → **다시 구성**에서 바꿀 수 있습니다.
공유기에서 스탠드를 **고정 IP(DHCP 예약)** 로 두는 것을 권장합니다.

## 동작 방식

스탠드는 UDP 5683 포트에서 보안 없는 CoAP 요청에 응답합니다(OCF/IoTivity 리소스).

| 리소스 | 값 |
|---|---|
| `/capability/switch/main/0` | `{"power": "on" \| "off"}` |
| `/capability/switchLevel/main/0` | `{"dimmingSetting": 1~100}` |
| `/capability/activityLightingMode/main/0` | `{"lightingMode": "reading" \| ...}` |
| `/oic/d` | 기기 정보(고유 ID, 이름) |

HA는 10초마다 위 리소스를 읽고, 명령은 `POST`로 보냅니다. 외부 서비스에는 연결하지 않습니다.

## 조명 모드 값 대응

| 앱 표시 | 기기 값 |
|---|---|
| 학습(언어) | `reading` (확인됨) |
| 학습(수리) | `writing` (확인됨) |
| 학습(멀티미디어) | `computer` (확인됨) |
| 야간 | `night` (확인됨) |
| 수면 | `sleepPreparation` (확인됨, 기기에 쓸 때는 `sleep`) |

기기가 위 목록에 없는 값을 보고하면 선택지에 자동으로 추가되어 표시됩니다.
값이 다르면 `custom_components/samsung_led_stand/const.py`의 `LIGHTING_MODES`를 고쳐 주세요.

## 문제 해결

- **등록할 때 "연결하지 못했어요"**: IP 확인, 스탠드 전원 확인, HA와 같은 네트워크(VLAN)인지 확인.
  Wi-Fi 격리(클라이언트 격리)가 켜져 있으면 UDP가 막힙니다.
- 직접 확인: HA 터미널에서 UDP 5683으로 CoAP GET 요청이 응답하는지 확인합니다.
- 로그: `custom_components.samsung_led_stand`를 debug로 설정하세요.

## 개발/테스트

```
pip install pytest-homeassistant-custom-component
pytest
```

실제 기기 없이 가짜 CoAP 서버로 통신·설정 흐름·엔티티를 검증합니다.

## 라이선스

MIT
