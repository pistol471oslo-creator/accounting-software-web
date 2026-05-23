"""
Database operations module for the accounting software.
Handles all database interactions with proper security and error handling.
"""

import sqlite3
import os
import shutil
from datetime import datetime
from typing import Optional, List, Tuple, Dict, Any
import bcrypt


class Database:
    """Database manager with context manager support."""
    
    def __init__(self, db_path: str = "database.db"):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self.cursor: Optional[sqlite3.Cursor] = None
        
    def __enter__(self):
        self.connect()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        
    def connect(self):
        """Establish database connection."""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._create_tables()
        
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
            self.cursor = None
            
    def _create_tables(self):
        """Create all necessary database tables."""
        tables = [
            '''CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'Cashier' CHECK(role IN ('Admin', 'Manager', 'Cashier', 'Viewer')),
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )''',
            
            '''CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT,
                address TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )''',
            
            '''CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                barcode TEXT UNIQUE,
                price REAL NOT NULL CHECK(price >= 0),
                cost_price REAL DEFAULT 0 CHECK(cost_price >= 0),
                stock INTEGER NOT NULL CHECK(stock >= 0),
                category TEXT DEFAULT 'عمومی',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )''',
            
            '''CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                total REAL NOT NULL CHECK(total >= 0),
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            )''',
            
            '''CREATE TABLE IF NOT EXISTS invoice_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                unit_price REAL NOT NULL CHECK(unit_price >= 0),
                FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
                FOREIGN KEY (product_id) REFERENCES products(id)
            )''',
            
            '''CREATE TABLE IF NOT EXISTS invoice_settings (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                header_text TEXT,
                footer_text TEXT,
                default_tax REAL CHECK(default_tax >= 0 AND default_tax <= 1),
                default_discount REAL CHECK(default_discount >= 0 AND default_discount <= 1),
                logo_path TEXT
            )''',
            
            '''CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                username TEXT,
                action TEXT,
                table_name TEXT,
                record_id INTEGER,
                details TEXT
            )'''
        ]
        
        for table_sql in tables:
            self.cursor.execute(table_sql)
        
        self.conn.commit()
        
    # ========== USER AUTHENTICATION ==========
    
    def hash_password(self, password: str) -> bytes:
        """Hash password using bcrypt."""
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    
    def verify_password(self, stored_hash: bytes, provided_password: str) -> bool:
        """Verify password against stored hash."""
        if isinstance(stored_hash, str):
            stored_hash = stored_hash.encode('utf-8')
        return bcrypt.checkpw(provided_password.encode('utf-8'), stored_hash)
    
    def register_user(self, username: str, password: str, role: str = None) -> Tuple[bool, str]:
        """
        Register a new user.
        First user is automatically Admin, others default to Cashier unless specified.
        Returns: (success: bool, message: str)
        """
        if not username or not password:
            return False, "نام کاربری و رمز عبور الزامی است"
        
        if len(password) < 8:
            return False, "رمز عبور باید حداقل ۸ کاراکتر باشد"
        
        # Validate role
        valid_roles = ['Admin', 'Manager', 'Cashier', 'Viewer']
        if role and role not in valid_roles:
            return False, f"نقش نامعتبر. نقش‌های معتبر: {', '.join(valid_roles)}"
        
        try:
            # Check if this is the first user
            self.cursor.execute("SELECT COUNT(*) FROM users")
            user_count = self.cursor.fetchone()[0]
            
            # First user is always Admin
            if user_count == 0:
                role = 'Admin'
            elif role is None:
                role = 'Cashier'  # Default role for new users
            
            password_hash = self.hash_password(password)
            self.cursor.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, password_hash, role)
            )
            self.conn.commit()
            self._log_audit(username, "USER_REGISTER", "users", self.cursor.lastrowid, f"User {username} registered with role {role}")
            return True, f"ثبت نام با موفقیت انجام شد (نقش: {role})"
        except sqlite3.IntegrityError:
            return False, "نام کاربری قبلاً استفاده شده است"
        except Exception as e:
            return False, f"خطا در ثبت نام: {str(e)}"
    
    def authenticate_user(self, username: str, password: str) -> Tuple[bool, str, Optional[str]]:
        """
        Authenticate a user.
        Returns: (success: bool, message: str, role: Optional[str])
        """
        if not username or not password:
            return False, "نام کاربری و رمز عبور الزامی است", None
        
        self.cursor.execute("SELECT password_hash, role FROM users WHERE username = ?", (username,))
        result = self.cursor.fetchone()
        
        if result and self.verify_password(result[0], password):
            role = result[1] if len(result) > 1 else 'Cashier'  # Default to Cashier for old users
            self._log_audit(username, "USER_LOGIN", "users", None, f"User {username} logged in (role: {role})")
            return True, "ورود موفق", role
        
        return False, "نام کاربری یا رمز عبور اشتباه است", None
    
    def user_count(self) -> int:
        """Get total number of users."""
        self.cursor.execute("SELECT COUNT(*) FROM users")
        return self.cursor.fetchone()[0]
    
    def get_user_role(self, username: str) -> Optional[str]:
        """Get user's role."""
        self.cursor.execute("SELECT role FROM users WHERE username = ?", (username,))
        result = self.cursor.fetchone()
        return result[0] if result else None
    
    def update_user_role(self, username: str, new_role: str, admin_username: str) -> Tuple[bool, str]:
        """
        Update user's role (Admin only).
        Returns: (success: bool, message: str)
        """
        valid_roles = ['Admin', 'Manager', 'Cashier', 'Viewer']
        
        if new_role not in valid_roles:
            return False, f"نقش نامعتبر. نقش‌های معتبر: {', '.join(valid_roles)}"
        
        try:
            self.cursor.execute(
                "UPDATE users SET role = ? WHERE username = ?",
                (new_role, username)
            )
            self.conn.commit()
            
            if self.cursor.rowcount > 0:
                self._log_audit(admin_username, "USER_ROLE_UPDATE", "users", None, 
                               f"Changed {username}'s role to {new_role}")
                return True, f"نقش کاربر {username} به {new_role} تغییر یافت"
            else:
                return False, "کاربر یافت نشد"
        except Exception as e:
            return False, f"خطا در تغییر نقش: {str(e)}"
    
    def get_all_users(self) -> List[Tuple]:
        """Get all users with their roles."""
        self.cursor.execute("SELECT username, role, created_at FROM users ORDER BY created_at DESC")
        return self.cursor.fetchall()
    
    def delete_user(self, username: str, admin_username: str) -> Tuple[bool, str]:
        """
        Delete a user (Admin only).
        Returns: (success: bool, message: str)
        """
        # Don't allow deleting yourself
        if username == admin_username:
            return False, "نمی‌توانید خودتان را حذف کنید"
        
        try:
            self.cursor.execute("DELETE FROM users WHERE username = ?", (username,))
            self.conn.commit()
            
            if self.cursor.rowcount > 0:
                self._log_audit(admin_username, "USER_DELETE", "users", None, 
                               f"Deleted user {username}")
                return True, f"کاربر {username} حذف شد"
            else:
                return False, "کاربر یافت نشد"
        except Exception as e:
            return False, f"خطا در حذف کاربر: {str(e)}"
    
    # ========== CUSTOMER OPERATIONS ==========
    
    def add_customer(self, name: str, phone: str = "", address: str = "") -> Tuple[bool, str, Optional[int]]:
        """
        Add a new customer.
        Returns: (success: bool, message: str, customer_id: Optional[int])
        """
        if not name or not name.strip():
            return False, "نام مشتری الزامی است", None
        
        # Validate phone number (basic validation)
        if phone and not self._validate_phone(phone):
            return False, "شماره تلفن نامعتبر است", None
        
        try:
            self.cursor.execute(
                "INSERT INTO customers (name, phone, address) VALUES (?, ?, ?)",
                (name.strip(), phone.strip(), address.strip())
            )
            self.conn.commit()
            customer_id = self.cursor.lastrowid
            self._log_audit(None, "CUSTOMER_ADD", "customers", customer_id, f"Added customer: {name}")
            return True, "مشتری با موفقیت ثبت شد", customer_id
        except Exception as e:
            return False, f"خطا در ثبت مشتری: {str(e)}", None
    
    def update_customer(self, customer_id: int, name: str, phone: str, address: str) -> Tuple[bool, str]:
        """Update customer information."""
        if not name or not name.strip():
            return False, "نام مشتری الزامی است"
        
        if phone and not self._validate_phone(phone):
            return False, "شماره تلفن نامعتبر است"
        
        try:
            self.cursor.execute(
                "UPDATE customers SET name=?, phone=?, address=? WHERE id=?",
                (name.strip(), phone.strip(), address.strip(), customer_id)
            )
            self.conn.commit()
            self._log_audit(None, "CUSTOMER_UPDATE", "customers", customer_id, f"Updated customer: {name}")
            return True, "مشتری با موفقیت به‌روزرسانی شد"
        except Exception as e:
            return False, f"خطا در به‌روزرسانی مشتری: {str(e)}"
    
    def delete_customer(self, customer_id: int) -> Tuple[bool, str]:
        """Delete a customer if they have no invoices."""
        try:
            # Check for invoices
            self.cursor.execute("SELECT COUNT(*) FROM invoices WHERE customer_id=?", (customer_id,))
            if self.cursor.fetchone()[0] > 0:
                return False, "این مشتری دارای فاکتور است و نمی‌توان حذف کرد"
            
            self.cursor.execute("DELETE FROM customers WHERE id=?", (customer_id,))
            self.conn.commit()
            self._log_audit(None, "CUSTOMER_DELETE", "customers", customer_id, f"Deleted customer ID: {customer_id}")
            return True, "مشتری با موفقیت حذف شد"
        except Exception as e:
            return False, f"خطا در حذف مشتری: {str(e)}"
    
    def search_customers(self, query: str = "") -> List[Tuple]:
        """Search customers by name or phone."""
        safe_query = f"%{query}%"
        self.cursor.execute(
            "SELECT * FROM customers WHERE name LIKE ? OR phone LIKE ? ORDER BY name",
            (safe_query, safe_query)
        )
        return self.cursor.fetchall()
    
    def get_customer(self, customer_id: int) -> Optional[Tuple]:
        """Get customer by ID."""
        self.cursor.execute("SELECT * FROM customers WHERE id=?", (customer_id,))
        return self.cursor.fetchone()
    
    def get_all_customers(self) -> List[Tuple]:
        """Get all customers ordered by name."""
        self.cursor.execute("SELECT id, name FROM customers ORDER BY name")
        return self.cursor.fetchall()
    
    # ========== PRODUCT OPERATIONS ==========
    
    def add_product(self, name: str, barcode: str, price: float, cost_price: float, 
                    stock: int, category: str = "عمومی") -> Tuple[bool, str, Optional[int]]:
        """
        Add a new product.
        Returns: (success: bool, message: str, product_id: Optional[int])
        """
        if not name or not name.strip():
            return False, "نام محصول الزامی است", None
        
        try:
            price = float(price)
            cost_price = float(cost_price) if cost_price else 0
            stock = int(stock)
            
            if price < 0:
                return False, "قیمت نمی‌تواند منفی باشد", None
            
            if cost_price < 0:
                return False, "قیمت خرید نمی‌تواند منفی باشد", None
            
            if stock < 0:
                return False, "موجودی نمی‌تواند منفی باشد", None
            
            # Just a warning, don't prevent adding
            # if cost_price > price:
            #     return False, "هشدار: قیمت خرید بیشتر از قیمت فروش است!", None
            
            self.cursor.execute(
                "INSERT INTO products (name, barcode, price, cost_price, stock, category) VALUES (?, ?, ?, ?, ?, ?)",
                (name.strip(), barcode.strip() if barcode else None, price, cost_price, stock, category.strip())
            )
            self.conn.commit()
            product_id = self.cursor.lastrowid
            self._log_audit(None, "PRODUCT_ADD", "products", product_id, f"Added product: {name}")
            return True, "محصول با موفقیت ثبت شد", product_id
        except ValueError:
            return False, "قیمت، قیمت خرید و موجودی باید عددی باشند", None
        except sqlite3.IntegrityError:
            return False, "بارکد تکراری است", None
        except Exception as e:
            return False, f"خطا در ثبت محصول: {str(e)}", None
    
    def update_product(self, product_id: int, name: str, barcode: str, price: float, 
                      cost_price: float, stock: int, category: str) -> Tuple[bool, str]:
        """Update product information."""
        if not name or not name.strip():
            return False, "نام محصول الزامی است"
        
        try:
            price = float(price)
            cost_price = float(cost_price) if cost_price else 0
            stock = int(stock)
            
            if price < 0 or cost_price < 0 or stock < 0:
                return False, "قیمت، قیمت خرید و موجودی نمی‌توانند منفی باشند"
            
            # Just a warning, don't prevent updating
            # if cost_price > price:
            #     return False, "هشدار: قیمت خرید بیشتر از قیمت فروش است!"
            
            self.cursor.execute(
                "UPDATE products SET name=?, barcode=?, price=?, cost_price=?, stock=?, category=? WHERE id=?",
                (name.strip(), barcode.strip() if barcode else None, price, cost_price, stock, category.strip(), product_id)
            )
            self.conn.commit()
            self._log_audit(None, "PRODUCT_UPDATE", "products", product_id, f"Updated product: {name}")
            return True, "محصول با موفقیت به‌روزرسانی شد"
        except ValueError:
            return False, "قیمت، قیمت خرید و موجودی باید عددی باشند"
        except sqlite3.IntegrityError:
            return False, "بارکد تکراری است"
        except Exception as e:
            return False, f"خطا در به‌روزرسانی محصول: {str(e)}"
    
    def delete_product(self, product_id: int) -> Tuple[bool, str]:
        """Delete a product (even if used in invoices)."""
        try:
            self.cursor.execute("DELETE FROM products WHERE id=?", (product_id,))
            self.conn.commit()
            self._log_audit(None, "PRODUCT_DELETE", "products", product_id, f"Deleted product ID: {product_id}")
            return True, "محصول با موفقیت حذف شد"
        except Exception as e:
            return False, f"خطا در حذف محصول: {str(e)}"
    
    def search_products(self, query: str = "") -> List[Tuple]:
        """Search products by name or barcode."""
        safe_query = f"%{query}%"
        self.cursor.execute(
            "SELECT * FROM products WHERE name LIKE ? OR barcode LIKE ? ORDER BY name",
            (safe_query, safe_query)
        )
        return self.cursor.fetchall()
    
    def get_product_by_barcode(self, barcode: str) -> Optional[Tuple]:
        """Get product by barcode."""
        self.cursor.execute("SELECT * FROM products WHERE barcode=?", (barcode,))
        return self.cursor.fetchone()
    
    def get_product(self, product_id: int) -> Optional[Tuple]:
        """Get product by ID."""
        self.cursor.execute("SELECT * FROM products WHERE id=?", (product_id,))
        return self.cursor.fetchone()
    
    def update_stock(self, product_id: int, quantity: int) -> Tuple[bool, str]:
        """Add to product stock."""
        if quantity <= 0:
            return False, "تعداد باید بیشتر از صفر باشد"
        
        try:
            self.cursor.execute(
                "UPDATE products SET stock = stock + ? WHERE id=?",
                (quantity, product_id)
            )
            self.conn.commit()
            self._log_audit(None, "STOCK_UPDATE", "products", product_id, f"Added {quantity} units to stock")
            return True, f"تعداد {quantity} به موجودی محصول اضافه شد"
        except Exception as e:
            return False, f"خطا در بروزرسانی موجودی: {str(e)}"
    
    def get_low_stock_products(self, threshold: int = 10) -> List[Tuple]:
        """Get products with stock below threshold."""
        self.cursor.execute(
            "SELECT * FROM products WHERE stock <= ? ORDER BY stock ASC",
            (threshold,)
        )
        return self.cursor.fetchall()
    
    def get_all_categories(self) -> List[str]:
        """Get list of all unique product categories."""
        self.cursor.execute("SELECT DISTINCT category FROM products ORDER BY category")
        return [row[0] for row in self.cursor.fetchall()]
    
    def search_products_by_category(self, category: str) -> List[Tuple]:
        """Search products by category."""
        self.cursor.execute(
            "SELECT * FROM products WHERE category = ? ORDER BY name",
            (category,)
        )
        return self.cursor.fetchall()
    
    def get_profit_report(self, start_date: str = None, end_date: str = None) -> Dict[str, Any]:
        """
        Calculate profit for a date range.
        Returns detailed profit breakdown.
        """
        try:
            # Build date filter
            date_filter = ""
            params = []
            
            if start_date and end_date:
                date_filter = "WHERE DATE(i.date) BETWEEN ? AND ?"
                params = [start_date, end_date]
            elif start_date:
                date_filter = "WHERE DATE(i.date) >= ?"
                params = [start_date]
            elif end_date:
                date_filter = "WHERE DATE(i.date) <= ?"
                params = [end_date]
            
            # Get sales data with cost information
            query = f"""
                SELECT 
                    ii.product_id,
                    p.name,
                    p.category,
                    SUM(ii.quantity) as total_sold,
                    SUM(ii.quantity * ii.unit_price) as total_revenue,
                    SUM(ii.quantity * p.cost_price) as total_cost,
                    p.cost_price,
                    ii.unit_price
                FROM invoice_items ii
                JOIN invoices i ON i.id = ii.invoice_id
                JOIN products p ON p.id = ii.product_id
                {date_filter}
                GROUP BY ii.product_id
                ORDER BY total_revenue DESC
            """
            
            self.cursor.execute(query, params)
            products = self.cursor.fetchall()
            
            total_revenue = 0
            total_cost = 0
            total_profit = 0
            
            product_details = []
            
            for product in products:
                product_id, name, category, qty_sold, revenue, cost, cost_price, sell_price = product
                profit = revenue - cost
                profit_margin = (profit / revenue * 100) if revenue > 0 else 0
                
                total_revenue += revenue
                total_cost += cost
                total_profit += profit
                
                product_details.append({
                    'id': product_id,
                    'name': name,
                    'category': category,
                    'quantity_sold': qty_sold,
                    'revenue': revenue,
                    'cost': cost,
                    'profit': profit,
                    'profit_margin': profit_margin,
                    'cost_price': cost_price,
                    'sell_price': sell_price
                })
            
            # Get invoice count
            count_query = f"""
                SELECT COUNT(DISTINCT i.id)
                FROM invoices i
                {date_filter}
            """
            self.cursor.execute(count_query, params)
            invoice_count = self.cursor.fetchone()[0]
            
            # Calculate profit margin
            overall_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0
            
            return {
                'total_revenue': total_revenue,
                'total_cost': total_cost,
                'total_profit': total_profit,
                'profit_margin': overall_margin,
                'invoice_count': invoice_count,
                'products': product_details,
                'start_date': start_date,
                'end_date': end_date
            }
            
        except Exception as e:
            return {
                'total_revenue': 0,
                'total_cost': 0,
                'total_profit': 0,
                'profit_margin': 0,
                'invoice_count': 0,
                'products': [],
                'error': str(e)
            }
    
    # ========== INVOICE OPERATIONS ==========
    
    def create_invoice(self, customer_id: int, items: List[Dict[str, Any]]) -> Tuple[bool, str, Optional[int]]:
        """
        Create a new invoice with items.
        items: List of dicts with keys: product_id, quantity
        Returns: (success: bool, message: str, invoice_id: Optional[int])
        """
        if not items:
            return False, "فاکتور باید حداقل یک محصول داشته باشد", None
        
        try:
            self.cursor.execute("BEGIN TRANSACTION")
            
            # Validate customer exists
            self.cursor.execute("SELECT id FROM customers WHERE id=?", (customer_id,))
            if not self.cursor.fetchone():
                self.conn.rollback()
                return False, "مشتری یافت نشد", None
            
            # Validate and calculate total
            total = 0
            validated_items = []
            
            for item in items:
                product_id = item['product_id']
                quantity = item['quantity']
                
                if quantity <= 0:
                    self.conn.rollback()
                    return False, "تعداد باید بیشتر از صفر باشد", None
                
                # Get product
                self.cursor.execute("SELECT id, name, price, stock FROM products WHERE id=?", (product_id,))
                product = self.cursor.fetchone()
                
                if not product:
                    self.conn.rollback()
                    return False, f"محصول با شناسه {product_id} یافت نشد", None
                
                _, name, price, stock = product
                
                if quantity > stock:
                    self.conn.rollback()
                    return False, f"موجودی کافی نیست! محصول: {name}, موجودی: {stock}", None
                
                validated_items.append({
                    'product_id': product_id,
                    'quantity': quantity,
                    'unit_price': price,
                    'subtotal': price * quantity
                })
                total += price * quantity
            
            # Create invoice
            self.cursor.execute(
                "INSERT INTO invoices (customer_id, date, total) VALUES (?, datetime('now'), ?)",
                (customer_id, total)
            )
            invoice_id = self.cursor.lastrowid
            
            # Add invoice items and update stock
            for item in validated_items:
                self.cursor.execute(
                    "INSERT INTO invoice_items (invoice_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
                    (invoice_id, item['product_id'], item['quantity'], item['unit_price'])
                )
                
                self.cursor.execute(
                    "UPDATE products SET stock = stock - ? WHERE id=?",
                    (item['quantity'], item['product_id'])
                )
            
            self.conn.commit()
            self._log_audit(None, "INVOICE_CREATE", "invoices", invoice_id, f"Created invoice with {len(items)} items, total: {total}")
            return True, f"فاکتور #{invoice_id} با موفقیت ثبت شد", invoice_id
            
        except Exception as e:
            self.conn.rollback()
            return False, f"خطا در ثبت فاکتور: {str(e)}", None
    
    def get_invoice(self, invoice_id: int) -> Optional[Dict]:
        """Get invoice with all details."""
        self.cursor.execute("""
            SELECT i.id, i.date, i.total, c.id, c.name, c.phone, c.address
            FROM invoices i
            JOIN customers c ON i.customer_id = c.id
            WHERE i.id = ?
        """, (invoice_id,))
        
        invoice_data = self.cursor.fetchone()
        if not invoice_data:
            return None
        
        # Get invoice items
        self.cursor.execute("""
            SELECT ii.id, ii.quantity, ii.unit_price, p.id, p.name, p.barcode
            FROM invoice_items ii
            JOIN products p ON ii.product_id = p.id
            WHERE ii.invoice_id = ?
        """, (invoice_id,))
        
        items = self.cursor.fetchall()
        
        return {
            'id': invoice_data[0],
            'date': invoice_data[1],
            'total': invoice_data[2],
            'customer': {
                'id': invoice_data[3],
                'name': invoice_data[4],
                'phone': invoice_data[5],
                'address': invoice_data[6]
            },
            'items': [
                {
                    'id': item[0],
                    'quantity': item[1],
                    'unit_price': item[2],
                    'product': {
                        'id': item[3],
                        'name': item[4],
                        'barcode': item[5]
                    }
                }
                for item in items
            ]
        }
    
    def get_customer_invoices(self, customer_id: int) -> List[Tuple]:
        """Get all invoices for a customer."""
        self.cursor.execute("""
            SELECT id, date, total
            FROM invoices
            WHERE customer_id = ?
            ORDER BY date DESC
        """, (customer_id,))
        return self.cursor.fetchall()
    
    def get_all_invoices(self, limit: int = 100) -> List[Tuple]:
        """Get all invoices with customer names."""
        self.cursor.execute("""
            SELECT i.id, i.date, i.total, c.name
            FROM invoices i
            JOIN customers c ON i.customer_id = c.id
            ORDER BY i.date DESC
            LIMIT ?
        """, (limit,))
        return self.cursor.fetchall()
    
    def delete_invoice(self, invoice_id: int) -> Tuple[bool, str]:
        """
        Delete an invoice WITHOUT restoring product stock.
        Returns: (success: bool, message: str)
        """
        try:
            self.cursor.execute("BEGIN TRANSACTION")
            
            # Check if invoice exists
            self.cursor.execute("SELECT id FROM invoices WHERE id = ?", (invoice_id,))
            if not self.cursor.fetchone():
                self.conn.rollback()
                return False, "فاکتور یافت نشد"
            
            # Delete invoice items
            self.cursor.execute("DELETE FROM invoice_items WHERE invoice_id = ?", (invoice_id,))
            
            # Delete invoice
            self.cursor.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))
            
            self.conn.commit()
            self._log_audit(None, "INVOICE_DELETE", "invoices", invoice_id, 
                          f"Deleted invoice {invoice_id}")
            return True, "فاکتور با موفقیت حذف شد"
            
        except Exception as e:
            self.conn.rollback()
            return False, f"خطا در حذف فاکتور: {str(e)}"
    
    def delete_all_customer_invoices(self, customer_id: int) -> Tuple[bool, str, int]:
        """
        Delete all invoices for a customer WITHOUT restoring product stock.
        Returns: (success: bool, message: str, count: int)
        """
        try:
            self.cursor.execute("BEGIN TRANSACTION")
            
            # Get all invoice IDs for this customer
            self.cursor.execute("""
                SELECT id FROM invoices WHERE customer_id = ?
            """, (customer_id,))
            invoice_ids = [row[0] for row in self.cursor.fetchall()]
            
            if not invoice_ids:
                self.conn.rollback()
                return False, "این مشتری فاکتوری ندارد", 0
            
            count = len(invoice_ids)
            
            # Delete all invoice items
            placeholders = ','.join('?' * len(invoice_ids))
            self.cursor.execute(f"""
                DELETE FROM invoice_items WHERE invoice_id IN ({placeholders})
            """, invoice_ids)
            
            # Delete all invoices
            self.cursor.execute(f"""
                DELETE FROM invoices WHERE customer_id = ?
            """, (customer_id,))
            
            self.conn.commit()
            self._log_audit(None, "INVOICE_DELETE_ALL", "invoices", customer_id, 
                          f"Deleted all {count} invoices for customer {customer_id}")
            return True, f"تمام {count} فاکتور با موفقیت حذف شد", count
            
        except Exception as e:
            self.conn.rollback()
            return False, f"خطا در حذف فاکتورها: {str(e)}", 0
    
    def get_daily_sales(self, date_str: str) -> Dict[str, Any]:
        """Get sales summary for a specific date."""
        # Validate date format
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            return None
        
        # Get invoice summary
        self.cursor.execute("""
            SELECT COUNT(id), COALESCE(SUM(total), 0)
            FROM invoices
            WHERE DATE(date) = ?
        """, (date_str,))
        invoice_count, total_sales = self.cursor.fetchone()
        
        # Get top product
        self.cursor.execute("""
            SELECT p.name, SUM(ii.quantity) as total_quantity
            FROM invoice_items ii
            JOIN invoices i ON i.id = ii.invoice_id
            JOIN products p ON p.id = ii.product_id
            WHERE DATE(i.date) = ?
            GROUP BY p.id
            ORDER BY total_quantity DESC
            LIMIT 1
        """, (date_str,))
        top_product = self.cursor.fetchone()
        
        # Get product details
        self.cursor.execute("""
            SELECT p.id, p.name, SUM(ii.quantity) as total_quantity, 
                   SUM(ii.quantity * ii.unit_price) as total_sales
            FROM invoice_items ii
            JOIN invoices i ON i.id = ii.invoice_id
            JOIN products p ON p.id = ii.product_id
            WHERE DATE(i.date) = ?
            GROUP BY p.id
            ORDER BY total_sales DESC
        """, (date_str,))
        products = self.cursor.fetchall()
        
        return {
            'date': date_str,
            'invoice_count': invoice_count or 0,
            'total_sales': total_sales or 0,
            'avg_invoice': (total_sales / invoice_count) if invoice_count > 0 else 0,
            'top_product': top_product[0] if top_product else None,
            'products': products
        }
    
    # ========== INVOICE SETTINGS ==========
    
    def get_invoice_settings(self) -> Dict[str, Any]:
        """Get invoice settings."""
        self.cursor.execute("SELECT * FROM invoice_settings WHERE id=1")
        settings = self.cursor.fetchone()
        
        if not settings:
            # Create default settings
            default_settings = {
                'header_text': 'فروشگاه نمونه\nتهران، خیابان اصلی\nتلفن: ۰۲۱-۱۲۳۴۵۶۷۸',
                'footer_text': 'با تشکر از خرید شما\nمهلت مرجوعی کالا ۷ روز می‌باشد',
                'default_tax': 0.09,
                'default_discount': 0.0,
                'logo_path': ''
            }
            
            self.cursor.execute("""
                INSERT INTO invoice_settings (id, header_text, footer_text, default_tax, default_discount, logo_path)
                VALUES (1, ?, ?, ?, ?, ?)
            """, (
                default_settings['header_text'],
                default_settings['footer_text'],
                default_settings['default_tax'],
                default_settings['default_discount'],
                default_settings['logo_path']
            ))
            self.conn.commit()
            return default_settings
        
        return {
            'header_text': settings[1],
            'footer_text': settings[2],
            'default_tax': settings[3],
            'default_discount': settings[4],
            'logo_path': settings[5]
        }
    
    def save_invoice_settings(self, settings: Dict[str, Any]) -> Tuple[bool, str]:
        """Save invoice settings."""
        try:
            self.cursor.execute("""
                UPDATE invoice_settings
                SET header_text=?, footer_text=?, default_tax=?, default_discount=?, logo_path=?
                WHERE id=1
            """, (
                settings['header_text'],
                settings['footer_text'],
                float(settings['default_tax']),
                float(settings['default_discount']),
                settings['logo_path']
            ))
            self.conn.commit()
            return True, "تنظیمات با موفقیت ذخیره شد"
        except Exception as e:
            return False, f"خطا در ذخیره تنظیمات: {str(e)}"
    
    # ========== REPORTS & ANALYTICS ==========
    
    def get_best_selling_products(self, start_date: str = None, end_date: str = None, limit: int = 10) -> List[Tuple]:
        """
        Get best-selling products by quantity sold in a date range.
        Returns: List of (product_name, total_quantity, total_revenue, avg_price, num_invoices)
        """
        try:
            query = """
                SELECT 
                    p.name,
                    SUM(ii.quantity) as total_quantity,
                    SUM(ii.quantity * ii.unit_price) as total_revenue,
                    AVG(ii.unit_price) as avg_price,
                    COUNT(DISTINCT ii.invoice_id) as num_invoices,
                    p.id
                FROM invoice_items ii
                JOIN products p ON ii.product_id = p.id
                JOIN invoices i ON ii.invoice_id = i.id
            """
            
            params = []
            if start_date and end_date:
                query += " WHERE i.date BETWEEN ? AND ?"
                params = [start_date, end_date]
            elif start_date:
                query += " WHERE i.date >= ?"
                params = [start_date]
            elif end_date:
                query += " WHERE i.date <= ?"
                params = [end_date]
            
            query += """
                GROUP BY p.id, p.name
                ORDER BY total_quantity DESC
                LIMIT ?
            """
            params.append(limit)
            
            self.cursor.execute(query, params)
            return self.cursor.fetchall()
        except Exception as e:
            print(f"Error getting best-selling products: {e}")
            return []
    
    def get_sales_by_date_range(self, start_date: str, end_date: str) -> Tuple[float, int, float]:
        """
        Get total sales, invoice count, and average invoice value for a date range.
        Returns: (total_sales, invoice_count, avg_invoice_value)
        """
        try:
            query = """
                SELECT 
                    SUM(total) as total_sales,
                    COUNT(*) as invoice_count,
                    AVG(total) as avg_invoice
                FROM invoices
                WHERE date BETWEEN ? AND ?
            """
            self.cursor.execute(query, (start_date, end_date))
            result = self.cursor.fetchone()
            
            if result and result[0]:
                return (result[0], result[1], result[2])
            return (0, 0, 0)
        except Exception as e:
            print(f"Error getting sales by date range: {e}")
            return (0, 0, 0)
    
    # ========== BACKUP/RESTORE ==========
    
    def create_backup(self) -> Tuple[bool, str, Optional[str]]:
        """Create a backup of the database."""
        try:
            backup_dir = "backups"
            if not os.path.exists(backup_dir):
                os.makedirs(backup_dir)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = os.path.join(backup_dir, f"database_backup_{timestamp}.db")
            
            # Close connection temporarily
            was_connected = self.conn is not None
            if was_connected:
                self.close()
            
            shutil.copy2(self.db_path, backup_file)
            
            # Reconnect if needed
            if was_connected:
                self.connect()
            
            self._log_audit(None, "BACKUP_CREATE", None, None, f"Created backup: {backup_file}")
            return True, "پشتیبان با موفقیت ایجاد شد", backup_file
        except Exception as e:
            return False, f"خطا در ایجاد پشتیبان: {str(e)}", None
    
    def restore_backup(self, backup_file: str) -> Tuple[bool, str]:
        """Restore database from backup."""
        try:
            if not os.path.exists(backup_file):
                return False, "فایل پشتیبان یافت نشد"
            
            # Create safety backup
            safety_backup = f"database_before_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            shutil.copy2(self.db_path, safety_backup)
            
            # Close connection
            self.close()
            
            # Restore
            shutil.copy2(backup_file, self.db_path)
            
            # Reconnect
            self.connect()
            
            self._log_audit(None, "BACKUP_RESTORE", None, None, f"Restored from: {backup_file}")
            return True, "بازیابی با موفقیت انجام شد"
        except Exception as e:
            return False, f"خطا در بازیابی: {str(e)}"
    
    # ========== EXPORT ==========
    
    def export_table_to_csv(self, table_name: str, filename: str) -> Tuple[bool, str]:
        """Export table data to CSV. Uses whitelist for security."""
        import csv
        
        # Whitelist of allowed tables
        allowed_tables = ['customers', 'products', 'invoices', 'invoice_items']
        
        if table_name not in allowed_tables:
            return False, "جدول مورد نظر مجاز نیست"
        
        try:
            # Safe to use table name now
            self.cursor.execute(f"SELECT * FROM {table_name}")
            rows = self.cursor.fetchall()
            
            if not rows:
                return False, "داده‌ای برای صادرات وجود ندارد"
            
            # Get column names
            self.cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [col[1] for col in self.cursor.fetchall()]
            
            with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(columns)
                writer.writerows(rows)
            
            self._log_audit(None, "EXPORT_CSV", table_name, None, f"Exported {table_name} to {filename}")
            return True, "صادرات با موفقیت انجام شد"
        except Exception as e:
            return False, f"خطا در صادرات: {str(e)}"
    
    # ========== AUDIT LOG ==========
    
    def _log_audit(self, username: Optional[str], action: str, table_name: Optional[str], 
                   record_id: Optional[int], details: str):
        """Log an audit entry."""
        try:
            self.cursor.execute("""
                INSERT INTO audit_log (username, action, table_name, record_id, details)
                VALUES (?, ?, ?, ?, ?)
            """, (username, action, table_name, record_id, details))
            self.conn.commit()
        except:
            pass  # Don't fail operations due to audit logging
    
    def get_audit_log(self, limit: int = 100) -> List[Tuple]:
        """Get recent audit log entries."""
        self.cursor.execute("""
            SELECT timestamp, username, action, table_name, record_id, details
            FROM audit_log
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
        return self.cursor.fetchall()
    
    # ========== HELPER METHODS ==========
    
    def _validate_phone(self, phone: str) -> bool:
        """Basic phone validation."""
        # Remove common separators
        cleaned = phone.replace('-', '').replace(' ', '').replace('(', '').replace(')', '')
        # Check if it's numeric and has reasonable length
        return cleaned.isdigit() and 7 <= len(cleaned) <= 15

    # ========== RETURNS & REFUNDS ==========

    def _ensure_returns_table(self):
        """Create returns table if it doesn't exist."""
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS returns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                refund_amount REAL DEFAULT 0,
                reason TEXT DEFAULT 'سایر',
                processed_by TEXT,
                status TEXT DEFAULT 'completed',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (invoice_id) REFERENCES invoices(id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            )
        """)
        self.conn.commit()

    def get_invoice_items_for_return(self, invoice_id: int) -> List[Tuple]:
        """Get invoice items available for return."""
        self._ensure_returns_table()
        self.cursor.execute("""
            SELECT ii.id, ii.product_id, p.name, ii.quantity, ii.unit_price,
                   (ii.quantity * ii.unit_price) as total
            FROM invoice_items ii
            JOIN products p ON p.id = ii.product_id
            WHERE ii.invoice_id = ?
        """, (invoice_id,))
        return self.cursor.fetchall()

    def process_return(self, invoice_id: int, product_id: int, quantity: int,
                       reason: str, refund_amount: float, processed_by: str, notes: str = "") -> Tuple[bool, str, Optional[int]]:
        """Process a product return."""
        self._ensure_returns_table()
        try:
            # Restore stock
            self.cursor.execute("UPDATE products SET stock = stock + ? WHERE id = ?", (quantity, product_id))
            # Record return
            self.cursor.execute("""
                INSERT INTO returns (invoice_id, product_id, quantity, refund_amount, reason, processed_by, status)
                VALUES (?, ?, ?, ?, ?, ?, 'completed')
            """, (invoice_id, product_id, quantity, refund_amount, reason, processed_by))
            self.conn.commit()
            return True, f"برگشت کالا با موفقیت ثبت شد", self.cursor.lastrowid
        except Exception as e:
            return False, f"خطا: {str(e)}", None

    def get_returns_history(self, limit: int = 100) -> List[Tuple]:
        """Get returns history."""
        self._ensure_returns_table()
        self.cursor.execute("""
            SELECT r.id, r.invoice_id, p.name, r.quantity, r.refund_amount,
                   r.reason, r.created_at, r.processed_by, r.status
            FROM returns r
            JOIN products p ON p.id = r.product_id
            ORDER BY r.created_at DESC
            LIMIT ?
        """, (limit,))
        return self.cursor.fetchall()
