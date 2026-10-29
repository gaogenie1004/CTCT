"""GAO Research AI private LLM backend. Requires separate hosting and OPENAI_API_KEY."""
import os
import json
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

API_KEY = os.getenv("OPENAI_API_KEY", "")
MODEL = os.getenv("GAO_MODEL", "gpt-4.1")
ACCESS_TOKEN = os.getenv("GAO_ACCESS_TOKEN", "")
ALLOWED_ORIGIN = os.getenv("GAO_ALLOWED_ORIGIN", "https://gaogenie1004.github.io")
MAX_BODY = 180000

def llm(system, user, max_tokens=5000):
    payload = json.dumps({"model": MODEL, "messages": [{"role":"system","content":system},{"role":"user","content":user}], "temperature":0.2, "max_tokens":max_tokens}).encode()
    request = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=payload, headers={"Authorization":"Bearer "+API_KEY,"Content-Type":"application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=100) as response:
        data=json.load(response)
    return data["choices"][0]["message"]["content"]

class Handler(BaseHTTPRequestHandler):
    def headers(self, status):
        self.send_response(status)
        origin=self.headers.get("Origin", "")
        if origin == ALLOWED_ORIGIN:
            self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
            self.send_header("Vary","Origin")
        self.send_header("Access-Control-Allow-Headers","Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods","POST, OPTIONS, GET")
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store")
        self.end_headers()
    def reply(self,status,obj):
        self.headers(status)
        self.wfile.write(json.dumps(obj,ensure_ascii=False).encode())
    def do_OPTIONS(self):
        self.headers(204)
    def do_GET(self):
        self.reply(200 if self.path=="/health" else 404,{"status":"ok"} if self.path=="/health" else {"error":"Not found"})
    def do_POST(self):
        if self.path!="/research":
            return self.reply(404,{"error":"Not found"})
        if not ACCESS_TOKEN or self.headers.get("Authorization","")!="Bearer "+ACCESS_TOKEN:
            return self.reply(401,{"error":"Access denied"})
        if not API_KEY:
            return self.reply(503,{"error":"Server OPENAI_API_KEY not configured"})
        try:
            n=int(self.headers.get("Content-Length","0"))
            if n<1 or n>MAX_BODY:
                return self.reply(413,{"error":"Invalid request size"})
            body=json.loads(self.rfile.read(n))
            papers=body.get("papers",[])[:45]
            if not isinstance(papers,list) or not papers:
                return self.reply(400,{"error":"Search sources required"})
            sources=[{"id":i+1,"title":str(p.get("title",""))[:300],"abstract":str(p.get("abstract",""))[:1200],"url":str(p.get("url",""))[:600],"kind":str(p.get("kind",""))[:80]} for i,p in enumerate(papers) if isinstance(p,dict)]
            topic=str(body.get("topic",""))[:300]
            question=str(body.get("question",""))[:700]
            source_json=json.dumps(sources,ensure_ascii=False)
            system="당신은 객관적인 한국어 전문 연구 분석가다. 제공된 출처 메타데이터만 근거로 분석하라. 외부 자료를 읽었다고 주장하지 마라. 각 중요한 주장에 [번호] 출처를 붙여라. 확인되지 않은 사항은 명시하라. 요약, 연구 질문, 조사 방법, 근거별 분석, 상충 가능성, 시나리오, 리스크, 결론, 검증 과제, 참고문헌을 포함하라."
            draft=llm(system,"주제: "+topic+"\n질문: "+question+"\n출처:\n"+source_json,6500)
            reviews=[]
            for role in ["방법론과 근거의 엄밀성","논리적 비약과 반론","인용의 정확성과 누락"]:
                critique=llm("당신은 "+role+"를 검토하는 독립 비평 역할의 AI다. 실제 교수라고 주장하지 마라. 아래 보고서의 구체적 문제와 수정 제안을 한국어로 5개 이내로 정리하라. 원문 검증이 불가능하면 명시하라.","보고서:\n"+draft[:23000]+"\n자료:\n"+source_json[:17000],1400)
                reviews.append({"perspective":role,"feedback":critique})
            revised=llm(system+" 세 가지 비평을 반영해 보고서를 개선하고, 검증하지 못한 사항은 유지·표시하라.","기존 보고서:\n"+draft+"\n검토 의견:\n"+json.dumps(reviews,ensure_ascii=False),6500)
            self.reply(200,{"report":revised,"reviews":reviews,"note":"AI 작성 및 3관점 비평 완료. 실제 교수 심사 또는 원문 검증은 아님."})
        except (ValueError,KeyError,urllib.error.URLError,TimeoutError) as e:
            self.reply(502,{"error":str(e)[:350]})
        except Exception:
            self.reply(500,{"error":"Internal processing error"})

if __name__=="__main__":
    port=int(os.getenv("PORT","8080"))
    ThreadingHTTPServer(("0.0.0.0",port),Handler).serve_forever()
