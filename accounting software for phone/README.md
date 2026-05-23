# 🌐 نرم‌افزار حسابداری - نسخه وب

## ✅ چگونه اجرا کنیم

### مرحله ۱ - نصب پیش‌نیازها
```bash
pip install flask bcrypt jdatetime
```

### مرحله ۲ - اجرا
```bash
python app.py
```

### مرحله ۳ - باز کردن در مرورگر
- کامپیوتر: http://localhost:5000
- موبایل (همان شبکه WiFi): http://YOUR_LAPTOP_IP:5000

## 📁 فایل‌ها
- `app.py` — سرور اصلی Flask
- `database.py` — عملیات پایگاه داده (از نسخه قبل)
- `persian_date.py` — تاریخ شمسی (از نسخه قبل)
- `database.db` — پایگاه داده شما (داده‌های قبلی موجود است)
- `templates/` — صفحات HTML

## 📱 دسترسی از موبایل
1. هر دو دستگاه روی یک WiFi باشند
2. IP لپ‌تاپ را پیدا کنید:
   - Windows: `ipconfig` → IPv4 Address
   - Mac/Linux: `ifconfig` یا `ip addr`
3. در مرورگر موبایل: `http://192.168.x.x:5000`

## 🔐 نقش‌ها
- **Admin** — دسترسی کامل
- **Manager** — بدون مدیریت کاربران
- **Cashier** — فقط فاکتور و مشتری
- **Viewer** — فقط گزارشات
