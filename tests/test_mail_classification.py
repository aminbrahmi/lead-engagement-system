import os
import json
import time
from typing import Dict, Tuple
from dotenv import load_dotenv

load_dotenv()

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

MODELS = {
    # GROQ - ULTRA RAPIDE ET GRATUIT
    "groq-llama-3.3-70b": {
        "provider": "groq",
        "model": "llama-3.3-70b-versatile",
        "free": True,
        "speed": "ultra_fast"
    },
    "groq-llama-3.1-70b": {
        "provider": "groq",
        "model": "llama-3.1-70b-versatile",
        "free": True,
        "speed": "ultra_fast"
    },
    "groq-mixtral-8x7b": {
        "provider": "groq",
        "model": "mixtral-8x7b-32768",
        "free": True,
        "speed": "ultra_fast"
    },
    "groq-gemma-2-9b": {
        "provider": "groq",
        "model": "gemma2-9b-it",
        "free": True,
        "speed": "ultra_fast"
    },
    
    # TOGETHER AI - Gratuit avec limits
    "together-llama-3.1-405b": {
        "provider": "together",
        "model": "meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo",
        "free": True,
        "speed": "fast"
    },
    "together-qwen-2.5-72b": {
        "provider": "together",
        "model": "Qwen/Qwen2.5-72B-Instruct-Turbo",
        "free": True,
        "speed": "fast"
    },
}

PROMPT = """Classify this email reply into ONE category:

Categories:
- interested: Positive response, wants to continue
- not_interested: Rejection, not interested
- info_request: Asking for more information
- out_of_office: Auto-reply, vacation
- bounce: Delivery failure
- neutral: Other responses

Email:
From: {from_addr}
Subject: {subject}
Body: {body}

Respond ONLY with JSON:
{{"category": "interested", "confidence": 0.95}}"""

TEST_EMAILS = [
    {
        "from_addr": "john@acme.com",
        "subject": "Re: AI Team",
        "body": "This sounds interesting! Can we schedule a call next week?",
        "expected": "interested"
    },
    {
        "from_addr": "jane@company.com",
        "subject": "Re: Your email",
        "body": "Thanks but we're not interested at this time.",
        "expected": "not_interested"
    },
    {
        "from_addr": "paul@startup.com",
        "subject": "Re: Demo",
        "body": "Can you send me pricing and case studies?",
        "expected": "info_request"
    },
    {
        "from_addr": "alice@corp.com",
        "subject": "Out of Office",
        "body": "I'm currently out of office until January 15th.",
        "expected": "out_of_office"
    },
    {
        "from_addr": "mailer-daemon@gmail.com",
        "subject": "Delivery Failed",
        "body": "Delivery to user@invalid.com failed permanently.",
        "expected": "bounce"
    },
    {
        "from_addr": "bob@startup.io",
        "subject": "Re: Partnership",
        "body": "Not a fit for us right now.",
        "expected": "not_interested"
    },
    {
        "from_addr": "emma@tech.com",
        "subject": "Re: Your solution",
        "body": "This could work for us. Let's discuss further.",
        "expected": "interested"
    },
    {
        "from_addr": "mike@corp.com",
        "subject": "Re: Demo request",
        "body": "What are your pricing tiers?",
        "expected": "info_request"
    },
    {
        "from_addr": "sarah@company.io",
        "subject": "Automatic reply",
        "body": "I'm away on vacation until next Monday.",
        "expected": "out_of_office"
    },
    {
        "from_addr": "postmaster@domain.com",
        "subject": "Undeliverable",
        "body": "User mailbox is full. Message rejected.",
        "expected": "bounce"
    },
]

# ══════════════════════════════════════════════════════════════════════════════
# PROVIDERS
# ══════════════════════════════════════════════════════════════════════════════

def classify_groq(model: str, email: Dict) -> Tuple[str, float, float]:
    """Groq - ULTRA RAPIDE ET GRATUIT"""
    from groq import Groq
    
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    
    prompt = PROMPT.format(**email)
    start = time.time()
    
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=100,
    )
    
    latency = (time.time() - start) * 1000
    
    result_text = response.choices[0].message.content.strip()
    if "```json" in result_text:
        result_text = result_text.split("```json")[1].split("```")[0].strip()
    elif "```" in result_text:
        result_text = result_text.split("```")[1].split("```")[0].strip()
    
    result = json.loads(result_text)
    return result["category"], result.get("confidence", 0.9), latency


def classify_together(model: str, email: Dict) -> Tuple[str, float, float]:
    """Together AI - Gratuit avec limits"""
    import requests
    
    api_key = os.getenv("TOGETHER_API_KEY")
    
    prompt = PROMPT.format(**email)
    start = time.time()
    
    response = requests.post(
        "https://api.together.xyz/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 100,
        }
    )
    
    latency = (time.time() - start) * 1000
    
    result_text = response.json()["choices"][0]["message"]["content"].strip()
    if "```json" in result_text:
        result_text = result_text.split("```json")[1].split("```")[0].strip()
    elif "```" in result_text:
        result_text = result_text.split("```")[1].split("```")[0].strip()
    
    result = json.loads(result_text)
    return result["category"], result.get("confidence", 0.9), latency


# ══════════════════════════════════════════════════════════════════════════════
# BENCHMARK
# ══════════════════════════════════════════════════════════════════════════════

def test_model(model_name: str, model_config: Dict):
    """Test un modèle sur tous les emails"""
    provider = model_config["provider"]
    model = model_config["model"]
    
    print(f"\n[{model_name}]")
    print(f"  Provider: {provider}")
    print(f"  Free: {'✅' if model_config['free'] else '❌'}")
    print(f"  Speed: {model_config['speed']}")
    
    results = []
    total_latency = 0
    errors = 0
    
    for email in TEST_EMAILS:
        try:
            if provider == "groq":
                category, confidence, latency = classify_groq(model, email)
            elif provider == "together":
                category, confidence, latency = classify_together(model, email)
            else:
                continue
            
            correct = category == email["expected"]
            results.append({
                "expected": email["expected"],
                "predicted": category,
                "confidence": confidence,
                "latency": latency,
                "correct": correct
            })
            
            total_latency += latency
            
            status = "✅" if correct else "❌"
            print(f"    {status} {email['expected']:15} → {category:15} ({confidence:.0%}) {latency:4.0f}ms")
            
        except Exception as e:
            errors += 1
            print(f"    ❌ ERROR: {e}")
    
    # Metrics
    if results:
        accuracy = sum(1 for r in results if r["correct"]) / len(results)
        avg_latency = total_latency / len(results)
        avg_confidence = sum(r["confidence"] for r in results) / len(results)
        
        print(f"\n  📊 Accuracy: {accuracy*100:.1f}%")
        print(f"  ⚡ Avg Latency: {avg_latency:.0f}ms")
        print(f"  🎯 Avg Confidence: {avg_confidence*100:.1f}%")
        print(f"  ❌ Errors: {errors}")
        
        return {
            "model": model_name,
            "provider": provider,
            "accuracy": accuracy,
            "avg_latency": avg_latency,
            "avg_confidence": avg_confidence,
            "errors": errors,
            "free": model_config["free"]
        }
    
    return None


def main():
    print("="*80)
    print(" 🚀 TEST DES MODÈLES LLM GRATUITS - CLASSIFICATION D'EMAILS")
    print("="*80)
    print(f"\n📧 Test emails: {len(TEST_EMAILS)}")
    print(f"🤖 Models: {len(MODELS)}")
    
    # Check API keys
    print("\n🔑 API Keys:")
    print(f"  GROQ: {'✅' if os.getenv('GROQ_API_KEY') else '❌ Missing'}")
    print(f"  TOGETHER: {'✅' if os.getenv('TOGETHER_API_KEY') else '❌ Missing'}")
    
    print("\n" + "="*80)
    
    # Test tous les modèles
    all_results = []
    
    for model_name, model_config in MODELS.items():
        result = test_model(model_name, model_config)
        if result:
            all_results.append(result)
    
    # Résumé
    if all_results:
        print("\n" + "="*80)
        print(" 📊 RÉSUMÉ - MODÈLES GRATUITS")
        print("="*80)
        print(f"\n{'Model':<30} {'Accuracy':>10} {'Latency':>10} {'Conf':>8} {'Free':>6}")
        print("-"*80)
        
        # Trier par accuracy
        all_results.sort(key=lambda x: x["accuracy"], reverse=True)
        
        for r in all_results:
            free_icon = "✅" if r["free"] else "❌"
            print(f"{r['model']:<30} {r['accuracy']*100:>9.1f}% {r['avg_latency']:>9.0f}ms {r['avg_confidence']*100:>7.1f}% {free_icon:>6}")
        
        print("="*80)
        
        # Winner
        winner = all_results[0]
        print(f"\n🏆 WINNER: {winner['model']}")
        print(f"   Accuracy: {winner['accuracy']*100:.1f}%")
        print(f"   Latency: {winner['avg_latency']:.0f}ms")
        print(f"   Confidence: {winner['avg_confidence']*100:.1f}%")
        print(f"   Provider: {winner['provider']}")
        print(f"   Free: {'YES ✅' if winner['free'] else 'NO'}")
        
        # Best free model
        free_models = [r for r in all_results if r["free"]]
        if free_models:
            best_free = free_models[0]
            print(f"\n💚 BEST FREE MODEL: {best_free['model']}")
            print(f"   Accuracy: {best_free['accuracy']*100:.1f}%")
            print(f"   Latency: {best_free['avg_latency']:.0f}ms")
            print(f"   Confidence: {best_free['avg_confidence']*100:.1f}%")
            
            # Recommendation
            print("\n💡 RECOMMENDATION FOR PRODUCTION:")
            print(f"   Model: {best_free['model']}")
            print(f"   Provider: {best_free['provider']}")
            print(f"   Cost: FREE ✅")
            print(f"   Speed: Ultra fast ⚡")
            print(f"   Accuracy: {best_free['accuracy']*100:.1f}%")
            
            print("\n📝 Update reply_classifier.py:")
            print(f"   PRIMARY_MODEL = '{best_free['model']}'")
            print(f"   PROVIDER = '{best_free['provider']}'")


if __name__ == "__main__":
    main()