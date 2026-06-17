import os, time, requests
from datetime import datetime
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

# ── Credentials (all from .env) ───────────────────────────────────────────────
RETELL_API_KEY  = os.getenv("RETELL_API_KEY")
RETELL_AGENT_ID = os.getenv("RETELL_AGENT_ID")
TWILIO_SID      = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN    = os.getenv("TWILIO_AUTH_TOKEN")
FROM_NUMBER     = os.getenv("FROM_NUMBER")

HEADERS = {
    "Authorization": f"Bearer {RETELL_API_KEY}",
    "Content-Type":  "application/json",
}

# ── Main function (called by FastAPI) ─────────────────────────────────────────
def make_verification_call(seller_number: str, seller_name: str = None) -> dict:
    """
    Places an outbound verification call to a seller via Twilio + Retell.
    Called by FastAPI with the seller's number from the scraper.
    Returns a dict with call results for FastAPI to store/forward.

    Args:
        seller_number: Seller's phone number e.g. "+971501234567"
        seller_name:   Optional seller name for logging

    Returns:
        dict with call_id, status, transcript, duration, timestamp
    """

    print("=" * 45)
    print("  VeriDrive — Verification Call")
    print("=" * 45)
    if seller_name:
        print(f"  Seller : {seller_name}")
    print(f"  Number : {seller_number}")
    print("=" * 45)

    # ── Step 1: Register call with Retell ─────────────────────────────────────
    print("\n📋 Registering call with Retell...")

    resp = requests.post(
        "https://api.retellai.com/v2/register-phone-call",
        headers=HEADERS,
        json={
            "agent_id":    RETELL_AGENT_ID,
            "from_number": FROM_NUMBER,
            "to_number":   seller_number,
            "direction":   "outbound",
        },
    )

    if resp.status_code not in (200, 201):
        error_msg = f"Failed to register call: {resp.status_code} — {resp.text}"
        print(f"❌ {error_msg}")
        return {
            "success":       False,
            "error":         error_msg,
            "seller_number": seller_number,
            "seller_name":   seller_name,
            "timestamp":     datetime.now().isoformat(),
        }

    call_data = resp.json()
    call_id   = call_data.get("call_id")

    if not call_id:
        error_msg = f"No call_id returned from Retell: {call_data}"
        print(f"❌ {error_msg}")
        return {
            "success":       False,
            "error":         error_msg,
            "seller_number": seller_number,
            "seller_name":   seller_name,
            "timestamp":     datetime.now().isoformat(),
        }

    sip_uri = f"sip:{call_id}@sip.retellai.com"
    print(f"✅ Registered — Call ID: {call_id}")

    # ── Step 2: Twilio places outbound call ───────────────────────────────────
    print(f"\n📞 Calling {seller_number}...")

    client = Client(TWILIO_SID, TWILIO_TOKEN)

    call = client.calls.create(
        to=seller_number,
        from_=FROM_NUMBER,
        twiml=f'<Response><Dial><Sip>{sip_uri}</Sip></Dial></Response>',
    )

    print(f"✅ Twilio call initiated — SID: {call.sid}")
    print("   Waiting for call to connect and complete...\n")

    # ── Step 3: Poll Retell for call status ───────────────────────────────────
    TERMINAL = {"ended", "error"}

    while True:
        r = requests.get(
            f"https://api.retellai.com/v2/get-call/{call_id}",
            headers=HEADERS,
        )

        if r.status_code != 200:
            print(f"\n❌ Error polling Retell: {r.status_code} — {r.text}")
            break

        info   = r.json()
        status = info.get("call_status", "unknown")
        print(f"   Status: {status}          ", end="\r")

        if status in TERMINAL:
            break

        time.sleep(5)

    print(f"\n\n📵 Call ended — Status: {status}")

    # ── Step 4: Fetch final transcript ────────────────────────────────────────
    print("\n⏳ Waiting 5s for Retell to finalise transcript...")
    time.sleep(5)

    r    = requests.get(
        f"https://api.retellai.com/v2/get-call/{call_id}",
        headers=HEADERS,
    )
    info       = r.json()
    transcript = info.get("transcript", "")
    duration   = info.get("duration_ms", 0) // 1000

    print(f"✅ Done — Duration: {duration}s")

    # ── Step 5: Return result dict to FastAPI ─────────────────────────────────
    return {
        "success":        status == "ended",
        "call_id":        call_id,
        "twilio_sid":     call.sid,
        "seller_number":  seller_number,
        "seller_name":    seller_name,
        "agent_id":       RETELL_AGENT_ID,
        "duration_s":     duration,
        "call_status":    status,
        "transcript":     transcript,
        "timestamp":      datetime.now().isoformat(),
    }


# ── Standalone test (run directly for testing only) ───────────────────────────
if __name__ == "__main__":
    import sys

    # Pass number as argument: python call_veridrive.py +971566131346
    # Or hardcode a test number below
    test_number = sys.argv[1] if len(sys.argv) > 1 else os.getenv("TEST_NUMBER")

    if not test_number:
        print("❌ Provide a number: python call_veridrive.py +971XXXXXXXXX")
        sys.exit(1)

    result = make_verification_call(test_number, seller_name="Test Seller")

    print("\n── Result ──────────────────────────────")
    for key, val in result.items():
        if key != "transcript":
            print(f"  {key}: {val}")
    print("\n── Transcript ──────────────────────────")
    print(result.get("transcript", "No transcript"))
