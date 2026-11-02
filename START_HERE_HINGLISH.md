# START HERE - bilkul shuru se (Hinglish guide)

Is project mein **dataset + poora code ready hai**. Tumhe sirf: install -> run -> API key lagana -> results -> GitHub -> video.
Jupyter ki zaroorat nahi, **VS Code** kaafi hai.

---

## PART 1 - Computer ko ready karo (ek baar)

1. **Python** install karo: python.org -> Downloads. Installer mein sabse pehle wala box **"Add Python to PATH"** zaroor tick karo.
2. **VS Code** install karo (code.visualstudio.com).
3. **Git** install karo (git-scm.com) - sab kuch "Next Next" karke.
4. Computer **restart** kar lo (taaki sab sahi se pehchana jaye).

## PART 2 - Project VS Code mein kholo

1. `student-support-agent.zip` ko **Extract** karo (right click -> Extract All).
2. VS Code kholo -> **File -> Open Folder** -> `student-support-agent` folder chuno.
3. Terminal kholo: **Terminal -> New Terminal** (neeche ek kaali/neeli window aayegi).
4. Ye commands **ek-ek karke** paste karo aur Enter dabao:

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```
(Mac ho to doosri line: `source venv/bin/activate`)

Agar "running scripts is disabled" error aaye (Windows): ye likho phir dobara activate karo
`Set-ExecutionPolicy -Scope Process Bypass`

Activate hone par line ke aage `(venv)` dikhna chahiye. Ye dikha = sab theek.

## PART 3 - Bina API key ke check karo (practice)

```
python tests/test_core.py
```
Last line `12/12 tests passed` aani chahiye.

```
streamlit run app.py
```
Browser khulega. Sidebar mein **Assignment 2** chuno -> User `S1001`, Password `Pass@1001` -> chat karo.
(Upar peela banner "MOCK model" dikhega - ye practice model hai, asli AI nahi.)

Band karne ke liye terminal mein **Ctrl + C**.

> Staff approval dekhne ke liye: Sign out -> User `STAFF01`, Password `Staff@123`.

## PART 4 - Asli AI model lagao (zaroori, warna marks nahi)

Mock model ke latency/token numbers **nakli** hain. Assignment ko real model chahiye.

1. Free key: **aistudio.google.com** -> Google se login -> **Get API key** -> key copy karo.
2. VS Code mein `.env.example` file ki **copy** banao aur naam rakho `.env`
   (terminal: `copy .env.example .env`).
3. `.env` kholo, `LLM_API_KEY=` ke aage apni key paste karo. Save (Ctrl+S).
4. App dobara chalao: `streamlit run app.py` -> upar **hara** banner "Real model active" dikhna chahiye.
5. Agar "model not found" aaye: Google AI Studio mein current Flash model ka naam dekho aur `LLM_MODEL=` mein daalo.
6. Agar "429 / rate limit" aaye: thoda ruko, ya eval mein `--pause 5` lagao.

**Key kisi ko mat dikhana, GitHub par mat daalna.** (`.env` file `.gitignore` se already blocked hai.)

## PART 5 - Evaluation chalao (accuracy, latency, tokens)

```
python run_eval.py --provider api --pause 3
```
5-10 minute lag sakte hain. Phir `results` folder kholo:
- `EVALUATION.md` -> final tables (A1 vs A2 comparison, trace table). **Yahi report/README mein dikhana hai.**
- `AUDIT_SAMPLE_A2.md` -> audit log table (Assignment 2 ka proof).
- Last mein `Key observations` mein 3 line **apne shabdon mein** likho (kya fail hua, kya sudhara).

Real model par kuch tests fail ho sakte hain (keyword check strict hai) - normal hai. Answer CSV mein padh ke
apni observation likho. Test phir se chalana ho to: `python run_eval.py --provider api --tests T01,T02`.

## PART 6 - GitHub par upload (sabse aasaan tareeka)

**Pehle check:** VS Code ke left side mein `.env` file **grey/faded** honi chahiye (matlab ignored). Aur `runtime` folder bhi.

### Tareeka A - VS Code se (recommended)
1. VS Code mein left icon **Source Control** (teen dots wala branch icon) kholo.
2. **Initialize Repository** dabao.
3. Message box mein likho `first version` -> **Commit** dabao (agar poochhe "stage all changes?" -> Yes).
4. **Publish Branch / Publish to GitHub** dabao -> GitHub login -> naam `student-support-agent` -> **Public repository** chuno.
5. Ho gaya. Browser mein github.com/<tumhara-username>/student-support-agent kholo.

### Tareeka B - Terminal se
1. github.com par **New repository** -> naam `student-support-agent` -> **Public** -> README/gitignore **mat** tick karo -> Create.
2. Jo URL mile (`https://github.com/<username>/student-support-agent.git`) wo copy karo. Terminal mein:

```
git init
git add .
git commit -m "Student support agent - assignments 1 and 2"
git branch -M main
git remote add origin https://github.com/<username>/student-support-agent.git
git push -u origin main
```
(`<username>` ki jagah apna GitHub username. Login ke liye browser khulega - password GitHub ab terminal mein nahi leta, browser se allow karo.)

Agar git "Please tell me who you are" bole:
```
git config --global user.name "Tumhara Naam"
git config --global user.email "tumhara@email.com"
```

### Upload ke baad zaroor check karo
1. GitHub page par **`.env` file nahi honi chahiye** (`.env.example` ho sakti hai - wo theek hai).
2. Browser ka **Incognito window** kholo, repo ka link daalo - khul gaya to repo public hai.
3. `results/` folder mein tumhare **real** eval ke files hon (mock wale nahi).

Baad mein kuch badla to: `git add .` -> `git commit -m "update"` -> `git push`.

## PART 7 - Video (har assignment ke liye)

Sirf screen recording nahi - **bolke samjhao** (OBS, Zoom ya Teams recording se). Ye order follow karo:

1. Problem + architecture (README ka diagram dikhao) - 1 min.
2. Agent flow: question -> redaction -> context selection -> model <-> tools -> answer -> trace.
3. Tools, memory, policy retrieval, context selection - code ke related files thoda scroll karke dikhao.
4. Live demo: README ke "Demo scenarios" table ke sab scenarios; har jawab ke neeche **Trace** expander kholo.
5. `results/EVALUATION.md`: accuracy, latency, token usage samjhao.
6. **Assignment 2 mein dikhana zaroori:** login, doosre student ka data **blocked**, phone change **approval required**,
   staff **Reject** -> execute nahi hua, staff **Approve** -> hua, OTP/password memory mein nahi, **audit log** table.
   Ye bhi bolo: "security rules Python code mein hain, sirf AI ke instruction par nahi" (`agent/tools.py` dikhao).
7. Last mein limitations (README section 6).

Video ko OneDrive/Google Drive par daalo -> **"Anyone with the link can view"** -> link incognito mein test karo.

## PART 8 - Submit

Mail wala Microsoft Form kholo, **GitHub link + video link** daalo.
**Deadline 31 Oct 2026 nikal chuki hai** - aaj hi Program Office (Jay Joshi) ko chhota mail bhejo ki late submission
accepted hai ya nahi, aur jaldi submit karo.

---

## Common errors

| Error | Matlab / solution |
| --- | --- |
| `python is not recognized` | Python install karte waqt PATH tick nahi hua. Dobara install karo (tick karke) ya `py` try karo. |
| `streamlit is not recognized` | `python -m streamlit run app.py` chalao. Aur `(venv)` activate hona chahiye. |
| `ModuleNotFoundError: openai` | `pip install -r requirements.txt` (venv activate karke). |
| Banner "MOCK model" hi dikhta hai | `.env` ka naam galat hai (`.env.txt` to nahi?) ya key khaali hai. Streamlit band karke dobara chalao. |
| `401 / invalid api key` | Key galat copy hui. Dobara copy karo, aage-peeche space nahi. |
| `429 / rate limit` | Free limit. 1 min ruko ya `--pause 5` lagao. |
| `model not found` | `.env` mein `LLM_MODEL` ko provider ki current model list se copy karo. |
| `git push` rejected | Repo mein README pehle se bana tha. `git pull origin main --allow-unrelated-histories` phir `git push`. |
| Data bigad gaya / fresh start | `runtime` folder delete karo. |
