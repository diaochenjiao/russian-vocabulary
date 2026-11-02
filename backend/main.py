from fastapi import FastAPI,UploadFile,HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import sqlite3,json,re,hashlib,os,datetime,subprocess
import fitz,pymorphy3,httpx
from dotenv import load_dotenv, set_key
from pydantic import BaseModel, SecretStr
from fastapi import Request
ROOT=Path(__file__).resolve().parents[1];DATA=ROOT/'data';DATA.mkdir(exist_ok=True)
load_dotenv(ROOT/'backend/.env');app=FastAPI();morph=pymorphy3.MorphAnalyzer()
from contextlib import contextmanager
@contextmanager
def db():
 c=sqlite3.connect(DATA/'study.db');c.row_factory=sqlite3.Row
 try:
  with c:yield c
 finally:c.close()
with db() as c:c.executescript('CREATE TABLE IF NOT EXISTS words(id INTEGER PRIMARY KEY,lemma TEXT UNIQUE,meaning TEXT,card TEXT);CREATE TABLE IF NOT EXISTS reviews(token TEXT PRIMARY KEY,word INTEGER,rating INTEGER,at TEXT);CREATE TABLE IF NOT EXISTS papers(id INTEGER PRIMARY KEY,name TEXT,year INTEGER,hash TEXT UNIQUE,status TEXT);CREATE TABLE IF NOT EXISTS hits(paper INTEGER,page INTEGER,form TEXT,lemma TEXT,candidates TEXT,context TEXT);CREATE TABLE IF NOT EXISTS cache(lemma TEXT PRIMARY KEY,content TEXT);')
with db() as c:
 existing={r[1] for r in c.execute('PRAGMA table_info(words)')}
 for name,typ in [('source_order','INTEGER'),('source','TEXT'),('page','INTEGER'),('ocr_text','TEXT'),('needs_review','INTEGER DEFAULT 0')]:
  if name not in existing:c.execute(f'ALTER TABLE words ADD COLUMN {name} {typ}')
@app.put('/api/words/{word_id}')
def update_word(word_id:int,w:dict):
 lemma=str(w.get('lemma','')).strip();meaning=str(w.get('meaning','')).strip()
 if not lemma or not meaning:raise HTTPException(400,'词条和释义不能为空')
 try:
  with db() as c:c.execute('UPDATE words SET lemma=?,meaning=?,needs_review=0 WHERE id=?',(lemma,meaning,word_id))
 except sqlite3.IntegrityError:raise HTTPException(409,'已有同名词条，请先检查')
 return {'ok':True}
@app.get('/api/vocabulary/source')
def vocabulary_source():
 p=DATA/'vocabulary-source.doc' if (DATA/'vocabulary-source.doc').exists() else DATA/'vocabulary-source.pdf'
 if not p.exists():raise HTTPException(404,'尚未导入原件')
 return FileResponse(p,media_type='application/msword' if p.suffix=='.doc' else 'application/pdf',filename=p.name)
def rows(sql,args=()):
 with db() as c:return [dict(r) for r in c.execute(sql,args)]
@app.get('/api/words')
def words():return rows('SELECT * FROM words ORDER BY COALESCE(source_order,id),id')
@app.post('/api/words')
def add(w:dict):
 with db() as c:c.execute('INSERT OR IGNORE INTO words(lemma,meaning) VALUES(?,?)',(w['lemma'],w.get('meaning','')))
 return {'ok':True}
@app.post('/api/import/{kind}')
async def upload(kind:str,file:UploadFile,year:int=0):
 raw=await file.read();digest=hashlib.sha256(raw).hexdigest();suffix=Path(file.filename).suffix.lower();path=DATA/(digest+suffix)
 if kind!='words' and rows('SELECT id FROM papers WHERE hash=?',(digest,)):raise HTTPException(409,'重复文件，未重复统计')
 if not path.exists():path.write_bytes(raw)
 if suffix=='.pdf':
  with fitz.open(path) as d:pages=[p.get_text() for p in d]
 elif suffix=='.docx':
  from docx import Document
  pages=['\n'.join(p.text for p in Document(path).paragraphs)]
 elif suffix=='.xlsx':
  from openpyxl import load_workbook
  pages=['\n'.join('\t'.join(str(v or '') for v in r) for r in load_workbook(path,data_only=True).active.values)]
 elif suffix in ['.txt','.csv']:pages=[raw.decode('utf-8-sig')]
 else:raise HTTPException(400,'不支持的格式')
 if kind=='words':
  found=[]
  for line in '\n'.join(pages).splitlines():
   m=re.search(r'([А-Яа-яЁё́-]+)\s*[,;\t ]*(.*)',line)
   if m:found.append({'lemma':m[1],'meaning':m[2]})
  return {'preview':found}
 if not year:raise HTTPException(400,'请指定年份')
 with db() as c:
  if c.execute('SELECT id FROM papers WHERE hash=?',(digest,)).fetchone():raise HTTPException(409,'重复文件')
  status='已索引' if any(re.search('[а-яА-Я]',p) for p in pages) else '需要 OCR，未纳入统计'
  pid=c.execute('INSERT INTO papers(name,year,hash,status) VALUES(?,?,?,?)',(file.filename,year,digest,status)).lastrowid
  for page,text in enumerate(pages,1):
   for m in re.finditer(r'[А-Яа-яЁё]+',text):
    form=m[0].lower();cand=sorted(set(p.normal_form for p in morph.parse(form)))
    c.execute('INSERT INTO hits VALUES(?,?,?,?,?,?)',(pid,page,form,cand[0] if len(cand)==1 else None,json.dumps(cand,ensure_ascii=False),text[max(0,m.start()-100):m.end()+100]))
 return {'status':status}
@app.get('/api/papers')
def papers():return rows('SELECT * FROM papers')
@app.get('/api/papers/{paper_id}/file')
def paper_file(paper_id:int):
 found=rows('SELECT * FROM papers WHERE id=?',(paper_id,))
 if not found:raise HTTPException(404,'试卷不存在')
 paths=list(DATA.glob(found[0]['hash']+'.pdf'))
 if not paths:raise HTTPException(404,'原文件不存在')
 return FileResponse(paths[0],media_type='application/pdf')
@app.get('/api/papers/{paper_id}/pages')
def paper_pages(paper_id:int):
 found=rows('SELECT * FROM papers WHERE id=?',(paper_id,))
 if not found:raise HTTPException(404,'试卷不存在')
 path=DATA/(found[0]['hash']+'.pages.json')
 return json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
@app.get('/api/frequency')
def frequency():return rows('SELECT lemma,count(*) count FROM hits WHERE lemma IS NOT NULL GROUP BY lemma ORDER BY count(*) DESC LIMIT 300')
@app.get('/api/dictionary')
def dictionary(q:str):return {'candidates':sorted(set(p.normal_form for p in morph.parse(q.lower()))),'local':rows('SELECT * FROM words WHERE lemma=?',(q,)),'hits':rows('SELECT hits.*,papers.name,papers.year FROM hits JOIN papers ON paper=papers.id WHERE lemma=? OR form=? OR candidates LIKE ?',(q,q,'%"'+q+'"%'))}
from zoneinfo import ZoneInfo
with db() as c:
 c.executescript('CREATE TABLE IF NOT EXISTS daily_tasks(day TEXT,word INTEGER,position INTEGER,completed INTEGER DEFAULT 0,PRIMARY KEY(day,word)); CREATE TABLE IF NOT EXISTS plan_settings(id INTEGER PRIMARY KEY,daily INTEGER); INSERT OR IGNORE INTO plan_settings VALUES(1,30);')
def today():return datetime.datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
def ensure_plan(c):
 day=today();limit=c.execute('SELECT daily FROM plan_settings WHERE id=1').fetchone()[0]
 count=c.execute('SELECT count(*) FROM daily_tasks WHERE day=?',(day,)).fetchone()[0]
 if count==0:
  for pos,w in enumerate(c.execute('SELECT id FROM words WHERE card IS NULL AND id NOT IN (SELECT word FROM daily_tasks WHERE completed=0 AND day<>?) ORDER BY COALESCE(source_order,id),id LIMIT ?',(day,limit)).fetchall()):
   c.execute('INSERT OR IGNORE INTO daily_tasks(day,word,position) VALUES(?,?,?)',(day,w[0],pos))
 # Unfinished old plans remain available as new words on the next day.
 if count==0:
  old=c.execute('SELECT word FROM daily_tasks WHERE day<>? AND completed=0 AND word IN (SELECT id FROM words WHERE card IS NULL) ORDER BY day,position LIMIT ?',(day,limit)).fetchall()
  for item in old:
   current=c.execute('SELECT count(*) FROM daily_tasks WHERE day=?',(day,)).fetchone()[0]
   if current>=limit:break
   c.execute('INSERT OR IGNORE INTO daily_tasks(day,word,position) VALUES(?,?,?)',(day,item[0],current))
 return day
@app.get('/api/plan')
def plan():
 with db() as c:
  day=ensure_plan(c)
  tasks=[dict(r) for r in c.execute('SELECT daily_tasks.*,words.lemma FROM daily_tasks JOIN words ON words.id=word WHERE day=? ORDER BY position',(day,))]
  groups=[]
  for i in range(0,len(tasks),10):
   part=tasks[i:i+10];groups.append({'group':i//10+1,'total':len(part),'completed':sum(t['completed'] for t in part)})
  return {'day':day,'daily':c.execute('SELECT daily FROM plan_settings WHERE id=1').fetchone()[0],'groups':groups,'total':len(tasks),'completed':sum(t['completed'] for t in tasks)}
@app.post('/api/plan')
def set_plan(r:dict):
 daily=r.get('daily')
 if not isinstance(daily,int) or not 0<=daily<=500:raise HTTPException(400,'每日新词范围为0–500')
 with db() as c:
  c.execute('UPDATE plan_settings SET daily=? WHERE id=1',(daily,))
 return {'message':'已保存，从明天的新计划生效；今日已安排的任务保留。'}
@app.get('/api/queue')
def queue(mode:str='learn',group:int=0):
 if mode=='learn':
  with db() as c:
   day=ensure_plan(c)
   return [dict(r) for r in c.execute('SELECT words.* FROM daily_tasks JOIN words ON words.id=word WHERE day=? AND completed=0 AND (?=0 OR CAST(position/10 AS INTEGER)=?-1) ORDER BY position',(day,group,group))]
 now=datetime.datetime.now(datetime.timezone.utc);due=[]
 for w in words():
  if w['card'] and datetime.datetime.fromisoformat(json.loads(w['card'])['due'].replace('Z','+00:00'))<=now:due.append(w)
 return sorted(due,key=lambda w:json.loads(w['card'])['due'])
@app.post('/api/review')
def review(r:dict):
 if r.get('rating') not in [1,2,3,4]:raise HTTPException(400,'评分错误')
 with db() as c:
  if c.execute('SELECT token FROM reviews WHERE token=?',(r['token'],)).fetchone():return {'ok':True}
  w=c.execute('SELECT * FROM words WHERE id=?',(r['id'],)).fetchone();now=datetime.datetime.now(datetime.timezone.utc).isoformat()
  p=subprocess.run(['node',str(ROOT/'frontend/schedule.mjs')],input=json.dumps({'card':json.loads(w['card']) if w['card'] else None,'rating':r['rating'],'now':now}),capture_output=True,text=True)
  if p.returncode:raise HTTPException(500,'FSRS 调度失败')
  card=p.stdout.strip();json.loads(card);c.execute('INSERT INTO reviews VALUES(?,?,?,?)',(r['token'],r['id'],r['rating'],now));c.execute('UPDATE words SET card=? WHERE id=?',(card,r['id']));c.execute('UPDATE daily_tasks SET completed=1 WHERE word=?',(r['id'],))
 return {'ok':True}
@app.get('/api/stats')
def stats():return {'words':len(words()),'reviews':rows('SELECT * FROM reviews ORDER BY at DESC'),'due':len(queue())}
@app.get('/api/ai/status')
def status():return {'configured':bool(os.getenv('DEEPSEEK_API_KEY')),'model':os.getenv('DEEPSEEK_MODEL','deepseek-flash')}
class APIConfig(BaseModel):
 api_key: SecretStr | None = None
 model: str = 'deepseek-flash'
@app.post('/api/ai/config')
def configure(config:APIConfig, request:Request):
 if request.headers.get('sec-fetch-site') == 'cross-site':raise HTTPException(403,'不允许跨站修改配置')
 model=config.model.strip()
 if not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',model):raise HTTPException(400,'模型名称格式错误')
 env=ROOT/'backend/.env'
 if config.api_key is not None:
  key=config.api_key.get_secret_value().strip()
  if not key or any(ch.isspace() for ch in key):raise HTTPException(400,'请输入有效的 API Key')
  set_key(str(env),'DEEPSEEK_API_KEY',key);os.environ['DEEPSEEK_API_KEY']=key
 set_key(str(env),'DEEPSEEK_MODEL',model);os.environ['DEEPSEEK_MODEL']=model
 return {'configured':bool(os.getenv('DEEPSEEK_API_KEY')),'model':model,'message':'配置已保存并立即生效'}
@app.post('/api/ai')
async def ai(r:dict):
 if not status()['configured']:raise HTTPException(400,'尚未配置 DeepSeek API，请在后端 .env 设置 DEEPSEEK_API_KEY。')
 q=r.get('q','测试');cached=rows('SELECT content FROM cache WHERE lemma=?',(q,))
 if cached and not r.get('refresh'):return json.loads(cached[0]['content'])
 try:
  async with httpx.AsyncClient(timeout=45) as client:
   res=await client.post(os.getenv('DEEPSEEK_BASE_URL','https://api.deepseek.com').rstrip('/')+'/chat/completions',headers={'Authorization':'Bearer '+os.environ['DEEPSEEK_API_KEY']},json={'model':status()['model'],'messages':[{'role':'system','content':'俄语中文词典。返回 JSON 对象，必须有 lemma 字符串和 chinese_meanings 字符串数组；可含语法、变格变位、例句。不要生成真题频率。'},{'role':'user','content':q}],'response_format':{'type':'json_object'},'max_tokens':1400})
  if res.status_code!=200:raise HTTPException(502,{401:'Key 无效',402:'余额不足',429:'限流',404:'模型或接口错误'}.get(res.status_code,'API 调用失败'))
  content=json.loads(res.json()['choices'][0]['message']['content'])
  if not isinstance(content.get('lemma'),str) or not isinstance(content.get('chinese_meanings'),list):raise ValueError()
  with db() as c:c.execute('INSERT OR REPLACE INTO cache VALUES(?,?)',(q,json.dumps(content,ensure_ascii=False)))
  return content
 except httpx.TimeoutException:raise HTTPException(504,'响应超时')
 except httpx.RequestError:raise HTTPException(502,'网络连接失败')
 except (ValueError,KeyError):raise HTTPException(502,'AI 数据结构无效，未缓存')
@app.get('/api/backup')
def backup():
 dest=DATA/'backup.sqlite'
 with db() as c:
  with sqlite3.connect(dest) as out:c.backup(out)
 return FileResponse(dest,filename='russian-study.sqlite')
import asyncio
speech_lock=asyncio.Semaphore(2)
@app.get('/api/pronunciation')
async def pronunciation(text:str):
 text=text.strip()
 if not text or len(text)>100 or not re.fullmatch(r'[А-Яа-яЁё́ -]+',text):raise HTTPException(400,'请输入100字以内的俄语词语')
 folder=DATA/'audio';folder.mkdir(exist_ok=True)
 target=folder/(hashlib.sha256(('ru-RU-SvetlanaNeural:'+text).encode()).hexdigest()+'.mp3')
 async with speech_lock:
  if not target.exists():
   import edge_tts,uuid
   temp=folder/(uuid.uuid4().hex+'.tmp')
   try:
    try:
     await asyncio.wait_for(edge_tts.Communicate(text,'ru-RU-SvetlanaNeural').save(str(temp)),timeout=8)
    except Exception:
     async with httpx.AsyncClient(timeout=15,follow_redirects=True) as client:
      response=await client.get('https://translate.google.com/translate_tts',params={'ie':'UTF-8','q':text,'tl':'ru','client':'tw-ob'})
      response.raise_for_status()
      if not response.headers.get('content-type','').startswith('audio/'):raise ValueError('invalid audio response')
      temp.write_bytes(response.content)
    if temp.stat().st_size<100:raise ValueError('empty audio')
    os.replace(temp,target)
   except Exception:
    temp.unlink(missing_ok=True)
    raise HTTPException(503,'在线俄语语音暂时不可用，请检查网络，或使用装有俄语语音包的系统浏览器。')
 return FileResponse(target,media_type='audio/mpeg')
class FavoriteInput(BaseModel):
 lemma:str
 meaning:str=''
@app.get('/api/favorites')
def favorites():
 return rows('SELECT * FROM favorites ORDER BY created_at DESC,lemma')
@app.post('/api/favorites')
def favorite_add(w:FavoriteInput):
 lemma=w.lemma.strip()
 if not lemma or len(lemma)>150 or len(w.meaning)>10000:raise HTTPException(400,'词条或释义长度不正确')
 with db() as c:
  local=c.execute('SELECT meaning FROM words WHERE lemma=? LIMIT 1',(lemma,)).fetchone()
  meaning=w.meaning or (local['meaning'] if local else '')
  c.execute('INSERT INTO favorites(lemma,meaning,created_at) VALUES(?,?,?) ON CONFLICT(lemma) DO UPDATE SET meaning=CASE WHEN excluded.meaning<>? THEN excluded.meaning ELSE favorites.meaning END',(lemma,meaning,datetime.datetime.now(datetime.timezone.utc).isoformat(),''))
 return {'ok':True}
@app.delete('/api/favorites/{lemma}')
def favorite_remove(lemma:str):
 with db() as c:c.execute('DELETE FROM favorites WHERE lemma=?',(lemma,))
 return {'ok':True}
with db() as c:c.execute('CREATE TABLE IF NOT EXISTS favorites(lemma TEXT PRIMARY KEY,meaning TEXT NOT NULL DEFAULT "",created_at TEXT NOT NULL)')
app.mount('/',StaticFiles(directory=ROOT/'frontend/dist',html=True),name='frontend')

