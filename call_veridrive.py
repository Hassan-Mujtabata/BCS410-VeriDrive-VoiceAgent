import os, time, requests
from datetime import datetime
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

# ── Credentials ───────────────────────────────────────────────────────────────
RETELL_API_KEY  = os.getenv("RETELL_API_KEY")
RETELL_AGENT_ID = os.getenv("RETELL_AGENT_ID")
TWILIO_SID      = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN    = os.getenv("TWILIO_AUTH_TOKEN")
FROM_NUMBER     = os.getenv("FROM_NUMBER")
YOUR_NUMBER     = os.getenv("YOUR_NUMBER")

HEADERS = {
    "Authorization": f"Bearer {RETELL_API_KEY}",
    "Content-Type":  "application/json",
}

print("=" * 45)
print("  VeriDrive — Phone Call Test")
print("=" * 45)

# ── Step 1: Pre-register call with Retell to get call_id + SIP URI ────────────
# Retell needs this so it knows which agent to activate when Twilio dials in.
print("📋 Registering call with Retell...")

resp = requests.post(
    "https://api.retellai.com/v2/register-phone-call",
    headers=HEADERS,
    json={
        "agent_id":   RETELL_AGENT_ID,
        "from_number": FROM_NUMBER,
        "to_number":   YOUR_NUMBER,
        "direction":   "outbound",
    },
)

if resp.status_code not in (200, 201):
    print(f"❌ Failed to register call: {resp.status_code}\n{resp.text}")
    exit(1)

call_data = resp.json()
call_id   = call_data.get("call_id")

if not call_id:
    print(f"❌ No call_id returned: {call_data}")
    exit(1)

# Retell's SIP URI for this specific call — valid for 5 minutes
sip_uri = f"sip:{call_id}@sip.retellai.com"
print(f"✅ Registered — Call ID: {call_id}")

# ── Step 2: Twilio calls your UAE number, bridges to Retell SIP on answer ─────
print(f"\n📞 Calling {YOUR_NUMBER} via Twilio...")
print(f"   When you pick up, Twilio connects to Retell via SIP → Vera activates.")
print(f"   Talk naturally — hang up when done.\n")

client = Client(TWILIO_SID, TWILIO_TOKEN)

call = client.calls.create(
    to=YOUR_NUMBER,
    from_=FROM_NUMBER,
    # When you answer, Twilio immediately dials Retell's SIP endpoint
    twiml=f'<Response><Dial><Sip>{sip_uri}</Sip></Dial></Response>',
)

print(f"✅ Twilio call initiated — SID: {call.sid}")
print("   Your phone is ringing. Pick up!\n")

# ── Step 3: Poll Retell (not Twilio) for call status ─────────────────────────
# Now that the call is registered in Retell, it shows up there.
TERMINAL = {"ended", "error"}

while True:
    r = requests.get(
        f"https://api.retellai.com/v2/get-call/{call_id}",
        headers=HEADERS,
    )
    if r.status_code != 200:
        print(f"\n❌ Error polling Retell: {r.status_code}\n{r.text}")
        break

    info   = r.json()
    status = info.get("call_status", "unknown")
    print(f"   Status: {status}          ", end="\r")

    if status in TERMINAL:
        break
    time.sleep(5)

print(f"\n\n📵 Call ended — Status: {status}")

if status != "ended":
    print("⚠️  Call did not complete cleanly. No transcript to save.")
    exit()

# ── Step 4: Fetch finalised transcript from Retell ────────────────────────────
print("\n⏳ Waiting 5s for Retell to finalise transcript...")
time.sleep(5)

r    = requests.get(
    f"https://api.retellai.com/v2/get-call/{call_id}",
    headers=HEADERS,
)
info       = r.json()
transcript = info.get("transcript", "No transcript available.")
duration   = info.get("duration_ms", 0) // 1000

# ── Step 5: Save transcript ───────────────────────────────────────────────────
filename = f"transcript_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

with open(filename, "w", encoding="utf-8") as f:
    f.write("VeriDrive Call Transcript\n")
    f.write("=" * 45 + "\n")
    f.write(f"Date      : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write(f"Call ID   : {call_id}\n")
    f.write(f"Agent ID  : {RETELL_AGENT_ID}\n")
    f.write(f"Duration  : {duration}s\n")
    f.write(f"Status    : {status}\n")
    f.write("=" * 45 + "\n\n")
    f.write(transcript)

print(f"✅ Transcript saved → {filename}")
print(f"   Duration : {duration}s | Call ID: {call_id}")
