# คู่มืออัปเดต Quant Signals V2

ใช้ GitHub repo และ Telegram Bot เดิมได้ ไม่ต้องสร้างใหม่

## 1. อัปโหลดไฟล์

แตก ZIP แล้วอัปโหลดไฟล์ด้านในไปแทนไฟล์เดิม อย่าอัปโหลด ZIP อย่างเดียว

ตรวจว่า `main.py` อยู่ที่หน้าแรกของ repo และ Workflow อยู่ที่:

```text
.github/workflows/alerts.yml
```

ไม่ใช่ `workflows/alerts.yml` ที่หน้าแรก

ถ้าไม่เห็น `.github` ให้คัดลอกข้อความจาก `WORKFLOW_COPY_FOR_GITHUB.txt`
ไปใส่ในไฟล์ `.github/workflows/alerts.yml` ผ่าน GitHub: Add file -> Create new file

ใน repo ต้องมีโฟลเดอร์ใหม่ `quant_alert/` และ `tests_v2/`

## 2. Secrets

ใช้ Secrets เดิม ไม่ต้องลบ:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

V2 ไม่ใช้ `SEC_USER_AGENT`

## 3. ทดสอบ

ไปที่ Actions -> Quant Signals V2 -> Run workflow

```text
Branch: main (or your default branch)
mode: demo
dry_run: false
```

Demo เป็นข้อมูลสมมติ ไม่ใช่หุ้นจริง

เมื่อได้รับข้อความแล้ว ให้กด Run workflow ใหม่ แล้วเปลี่ยนเป็น:

```text
mode: manual
dry_run: false
```

อย่ากด Re-run all jobs ในรอบ Demo เดิม

ไม่ติ๊ก dry_run ถ้าต้องการให้ส่งเข้า Telegram

## 4. ตรวจผล

ข้อความต้องขึ้น `Model quant-signals-v2.0.0`

ถ้า Price usable ยัง 0 ให้ดู `diagnostics.json` ใน Artifacts ของรอบนั้น

ถ้าไม่มีสัญญาณผ่านเกณฑ์ ระบบจะไม่ฝืนเลือกหุ้น

V2 ไม่ใช้ Fundamental เป็นเงื่อนไขหลัก และไม่ได้ตรวจข่าวอัตโนมัติ

ไม่มีการซื้อขายอัตโนมัติ และไม่รับรองกำไร

รายละเอียด: README.md, docs/SETUP.md, docs/SIGNAL_RULES.md, docs/VALIDATION.md
