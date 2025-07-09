# main.py - Complete Optimized FastAPI Backend with Supabase Integration
import os
import uuid
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Depends, Header, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import supabase after loading env
try:
    from supabase import create_client, Client
    
    # Supabase Configuration
    SUPABASE_URL = os.getenv("SUPABASE_URL", "https://etxqtocatvqeombnbufk.supabase.co")
    SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImV0eHF0b2NhdHZxZW9tYm5idWZrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTE3NTA4ODUsImV4cCI6MjA2NzMyNjg4NX0.S1bUwbOLJARZAuxFgeALD1mQk59vsIL-Cw_JFqK1_WQ")
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print(f"✅ Connected to Supabase: {SUPABASE_URL}")
except Exception as e:
    print(f"❌ Supabase connection error: {e}")
    supabase = None

app = FastAPI(title="Charkop Vegetables API", debug=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# File upload setup
UPLOADS_DIR = Path("uploads")
for directory in [UPLOADS_DIR, UPLOADS_DIR / "banners", UPLOADS_DIR / "products", UPLOADS_DIR / "categories"]:
    directory.mkdir(exist_ok=True)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Pydantic Models
class UserRegister(BaseModel):
    name: str
    phone: str
    password: str

class UserLogin(BaseModel):
    phone: str
    password: str

class CartItem(BaseModel):
    product_id: str
    quantity: int = 1
    selected_weight: str = "500g"
    selected_unit: int = 1

class OrderCreate(BaseModel):
    delivery_slot: str
    delivery_date: str
    delivery_address: Dict[str, Any]
    payment_method: str
    special_instructions: Optional[str] = None

# Direct Supabase Helper Functions (Fixed for v2.16.0)
def get_table_data(table_name: str, filters: Dict = None, columns: str = "*"):
    """Get data from table with optional filters"""
    try:
        response = supabase.table(table_name).select(columns).execute()
        
        if response.data and filters:
            # Apply filters manually
            filtered_data = []
            for item in response.data:
                match = True
                for key, value in filters.items():
                    if str(item.get(key)) != str(value):
                        match = False
                        break
                if match:
                    filtered_data.append(item)
            return filtered_data
        
        return response.data or []
    except Exception as e:
        print(f"Get table data error: {e}")
        return []

def insert_table_data(table_name: str, data: Dict):
    """Insert data into table"""
    try:
        response = supabase.table(table_name).insert(data).execute()
        return response
    except Exception as e:
        print(f"Insert data error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def update_table_data(table_name: str, data: Dict, filters: Dict):
    """Update data in table"""
    try:
        # Get existing records
        existing_records = get_table_data(table_name, filters)
        
        if existing_records:
            # Update first matching record
            record = existing_records[0]
            updated_data = {**record, **data}
            response = supabase.table(table_name).upsert(updated_data).execute()
            return response
        
        return None
    except Exception as e:
        print(f"Update data error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def delete_table_data(table_name: str, filters: Dict):
    """Delete data from table"""
    try:
        # Get records to delete
        records = get_table_data(table_name, filters)
        
        for record in records:
            if 'id' in record:
                supabase.table(table_name).delete().eq('id', record['id']).execute()
        
        return True
    except Exception as e:
        print(f"Delete data error: {e}")
        return False

# File Management Helper
class FileManager:
    @staticmethod
    def validate_image(file: UploadFile):
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")
        
        allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
        if not any(file.filename.lower().endswith(ext) for ext in allowed_extensions):
            raise HTTPException(status_code=400, detail=f"Invalid file type. Allowed: {', '.join(allowed_extensions)}")
        
        file.file.seek(0, 2)
        if file.file.tell() > 5 * 1024 * 1024:  # 5MB
            raise HTTPException(status_code=400, detail="File too large. Max size: 5MB")
        file.file.seek(0)

    @staticmethod
    def save_file(file: UploadFile, directory: Path, filename: str = None) -> str:
        if not filename:
            ext = os.path.splitext(file.filename)[1] if file.filename else ""
            filename = f"{uuid.uuid4()}{ext}"
        
        file_path = directory / filename
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        return f"/uploads/{directory.name}/{filename}"

    @staticmethod
    def delete_file(file_path: str):
        if file_path and file_path.startswith("/uploads/"):
            full_path = Path(".") / file_path[1:]
            if full_path.exists():
                full_path.unlink()

# Authentication Helper
class Auth:
    @staticmethod
    def get_current_user(authorization: Optional[str] = None) -> Optional[Dict]:
        if not authorization or not authorization.startswith("Bearer "):
            return None
        
        try:
            token = authorization.split(" ")[1]
            tokens = get_table_data("tokens", {"token": token})
            
            if tokens:
                phone = tokens[0]["phone"]
                users = get_table_data("users", {"phone": phone})
                return users[0] if users else None
        except Exception as e:
            print(f"Auth error: {e}")
            pass
        return None

# Root endpoints
@app.get("/")
def root():
    return {
        "message": "🥬 Charkop Vegetables API - Supabase Optimized",
        "status": "running",
        "version": "3.0.0",
        "database": "supabase",
        "supabase_connected": supabase is not None,
        "features": ["image_upload", "banners", "enhanced_admin", "supabase_integration"],
        "docs": "http://localhost:8000/docs"
    }

@app.get("/health")
def health_check():
    try:
        if supabase:
            # Simple test query
            result = supabase.table("categories").select("id").limit(1).execute()
            
            if result.data:
                return {
                    "status": "healthy",
                    "service": "charkop-vegetables-api",
                    "timestamp": datetime.now().isoformat(),
                    "database": "supabase-connected",
                    "supabase_url": SUPABASE_URL,
                    "tables_accessible": True
                }
            else:
                return {
                    "status": "database-empty",
                    "service": "charkop-vegetables-api", 
                    "timestamp": datetime.now().isoformat(),
                    "database": "supabase-connected-but-empty",
                    "supabase_url": SUPABASE_URL
                }
    except Exception as e:
        return {
            "status": "database-error", 
            "error": str(e),
            "supabase_url": SUPABASE_URL,
            "timestamp": datetime.now().isoformat()
        }
    
    return {
        "status": "no-database",
        "message": "Supabase not configured",
        "timestamp": datetime.now().isoformat()
    }

# Authentication endpoints
@app.post("/auth/register")
def register_user(user_data: UserRegister):
    """Register new user"""
    try:
        # Check if user exists
        existing_users = get_table_data("users", {"phone": user_data.phone})
        if existing_users:
            raise HTTPException(status_code=400, detail="Phone number already registered")
        
        if len(user_data.phone) < 10 or len(user_data.password) < 6:
            raise HTTPException(status_code=400, detail="Invalid phone or password length")
        
        user = {
            "name": user_data.name,
            "phone": user_data.phone,
            "password": user_data.password,  # Hash in production
            "is_active": True,
            "is_verified": False,
            "created_at": datetime.now().isoformat()
        }
        
        result = insert_table_data("users", user)
        return {"message": "User registered successfully", "user": result.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")

@app.post("/auth/login")
def login_user(credentials: UserLogin):
    """Login user"""
    try:
        users = get_table_data("users", {"phone": credentials.phone})
        
        if not users or users[0]["password"] != credentials.password:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        user = users[0]
        if not user["is_active"]:
            raise HTTPException(status_code=401, detail="Account deactivated")
        
        token = f"token_{credentials.phone}_{uuid.uuid4().hex[:8]}"
        insert_table_data("tokens", {"token": token, "phone": credentials.phone})
        
        return {"access_token": token, "token_type": "bearer"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

@app.get("/auth/me")
def get_current_user_info(authorization: Optional[str] = Header(None)):
    """Get current user info"""
    user = Auth.get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user

# Categories endpoints
@app.get("/categories")
def get_categories():
    """Get all active categories"""
    try:
        categories = get_table_data("categories", {"is_active": True})
        return sorted(categories, key=lambda x: x.get("display_order", 0))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching categories: {str(e)}")

@app.get("/categories/{category_id}")
def get_category(category_id: str):
    """Get specific category"""
    try:
        categories = get_table_data("categories", {"id": category_id})
        if not categories:
            raise HTTPException(status_code=404, detail="Category not found")
        return categories[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching category: {str(e)}")

# Products endpoints
@app.get("/products")
def get_products(category_id: Optional[str] = None, featured: Optional[bool] = None, 
                search: Optional[str] = None, skip: int = 0, limit: int = 100):
    """Get products with filters"""
    try:
        # Get all active products
        products = get_table_data("products", {"is_active": True})
        
        # Apply filters
        if category_id:
            products = [p for p in products if p.get("category_id") == category_id]
        
        if featured is not None:
            products = [p for p in products if p.get("featured", False) == featured]
        
        if search:
            search_lower = search.lower()
            products = [p for p in products if search_lower in p["name"].lower() or 
                       search_lower in p.get("description", "").lower()]
        
        return products[skip:skip + limit]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching products: {str(e)}")

@app.get("/products/{product_id}")
def get_product(product_id: str):
    """Get specific product"""
    try:
        products = get_table_data("products", {"id": product_id, "is_active": True})
        if not products:
            raise HTTPException(status_code=404, detail="Product not found")
        return products[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching product: {str(e)}")

# Banners endpoints
@app.get("/banners")
def get_banners():
    """Get all active banners"""
    try:
        banners = get_table_data("banners", {"is_active": True})
        return sorted(banners, key=lambda x: x.get("display_order", 0))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching banners: {str(e)}")

# Cart endpoints
@app.get("/cart")
def get_cart(authorization: Optional[str] = Header(None)):
    """Get user's cart"""
    user = Auth.get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        cart_items = get_table_data("cart_items", {"user_id": user["id"]})
        return cart_items
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching cart: {str(e)}")

@app.post("/cart")
def add_to_cart(cart_item: CartItem, authorization: Optional[str] = Header(None)):
    """Add item to cart"""
    user = Auth.get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        # Check product exists
        products = get_table_data("products", {"id": cart_item.product_id})
        if not products:
            raise HTTPException(status_code=404, detail="Product not found")
        
        product = products[0]
        if product["stock_quantity"] < cart_item.quantity:
            raise HTTPException(status_code=400, detail="Insufficient stock")
        
        # Check if item already exists in cart
        existing_items = get_table_data("cart_items", {
            "user_id": user["id"],
            "product_id": cart_item.product_id,
            "selected_weight": cart_item.selected_weight,
            "selected_unit": cart_item.selected_unit
        })
        
        if existing_items:
            # Update existing item
            existing_item = existing_items[0]
            new_quantity = existing_item["quantity"] + cart_item.quantity
            update_data = {
                "quantity": new_quantity,
                "updated_at": datetime.now().isoformat()
            }
            update_table_data("cart_items", update_data, {"id": existing_item["id"]})
            return {"message": "Cart updated", "item": {**existing_item, **update_data}}
        else:
            # Create new item
            new_item = {
                "user_id": user["id"],
                "product_id": cart_item.product_id,
                "quantity": cart_item.quantity,
                "selected_weight": cart_item.selected_weight,
                "selected_unit": cart_item.selected_unit,
                "created_at": datetime.now().isoformat()
            }
            result = insert_table_data("cart_items", new_item)
            return result.data[0] if result.data else {"message": "Added to cart"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding to cart: {str(e)}")

@app.delete("/cart/{cart_item_id}")
def remove_cart_item(cart_item_id: str, authorization: Optional[str] = Header(None)):
    """Remove item from cart"""
    user = Auth.get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        delete_table_data("cart_items", {"id": cart_item_id, "user_id": user["id"]})
        return {"message": "Item removed from cart"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error removing from cart: {str(e)}")

# Orders endpoints
@app.post("/orders")
def create_order(order_data: OrderCreate, authorization: Optional[str] = Header(None)):
    """Create new order"""
    user = Auth.get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        # Get cart items
        cart_items = get_table_data("cart_items", {"user_id": user["id"]})
        if not cart_items:
            raise HTTPException(status_code=400, detail="Cart is empty")
        
        # Calculate totals and create order items
        total_amount = 0.0
        order_items = []
        
        for cart_item in cart_items:
            # Get product info
            products = get_table_data("products", {"id": cart_item["product_id"]})
            
            if products:
                product = products[0]
                item_total = float(product["base_price"]) * cart_item["quantity"] * cart_item["selected_unit"]
                total_amount += item_total
                
                order_items.append({
                    "product_id": cart_item["product_id"],
                    "product_name": product["name"],
                    "quantity": cart_item["quantity"],
                    "unit_price": float(product["base_price"]),
                    "total_price": item_total,
                    "selected_weight": cart_item["selected_weight"],
                    "selected_unit": cart_item["selected_unit"]
                })
        
        # Calculate delivery charges
        delivery_charges = 0.0 if total_amount >= 199 else 40.0
        final_amount = total_amount + delivery_charges
        
        # Generate order number
        existing_orders = get_table_data("orders", {"user_id": user["id"]})
        order_number = f"ORD{len(existing_orders) + 1:03d}{user['id'][-3:]}"
        
        # Create order
        order = {
            "order_number": order_number,
            "user_id": user["id"],
            "total_amount": total_amount,
            "delivery_charges": delivery_charges,
            "final_amount": final_amount,
            "status": "pending",
            "delivery_slot": order_data.delivery_slot,
            "delivery_date": order_data.delivery_date,
            "delivery_address": order_data.delivery_address,
            "payment_method": order_data.payment_method,
            "payment_status": "pending",
            "special_instructions": order_data.special_instructions,
            "items": order_items,
            "created_at": datetime.now().isoformat()
        }
        
        # Insert order
        result = insert_table_data("orders", order)
        
        # Clear cart
        delete_table_data("cart_items", {"user_id": user["id"]})
        
        return result.data[0] if result.data else {"message": "Order created successfully", "order": order}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Order creation error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error creating order: {str(e)}")

@app.get("/orders")
def get_orders(authorization: Optional[str] = Header(None)):
    """Get user's orders"""
    user = Auth.get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        orders = get_table_data("orders", {"user_id": user["id"]})
        # Sort by creation date (newest first)
        return sorted(orders, key=lambda x: x.get("created_at", ""), reverse=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching orders: {str(e)}")

# Admin endpoints
@app.get("/admin/stats")
def get_admin_stats():
    """Get basic admin statistics"""
    try:
        stats = {
            "users": len(get_table_data("users")),
            "products": len(get_table_data("products")),
            "categories": len(get_table_data("categories")),
            "orders": len(get_table_data("orders")),
            "banners": len(get_table_data("banners"))
        }
        return stats
    except Exception as e:
        return {"error": f"Error fetching stats: {str(e)}"}

# File upload utility
@app.post("/admin/upload/image")
def upload_single_image(file: UploadFile = File(...), category: str = Form("general")):
    """Upload a single image file"""
    try:
        FileManager.validate_image(file)
        
        upload_dir = UPLOADS_DIR / {"products": "products", "categories": "categories", 
                                   "banners": "banners"}.get(category, "general")
        
        file_url = FileManager.save_file(file, upload_dir)
        return {"message": "Image uploaded successfully", "file_url": file_url, "category": category}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

# Admin CRUD endpoints
@app.post("/admin/products")
def create_product(
    name: str = Form(...), description: str = Form(...), category_id: str = Form(...),
    base_price: float = Form(...), stock_quantity: int = Form(...),
    featured: bool = Form(False), is_active: bool = Form(True),
    image: Optional[UploadFile] = File(None)
):
    """Create a new product"""
    try:
        # Handle image upload
        image_url = None
        if image and image.filename:
            FileManager.validate_image(image)
            image_url = FileManager.save_file(image, UPLOADS_DIR / "products")
        
        product_data = {
            "name": name, "description": description, "category_id": category_id,
            "base_price": base_price, "stock_quantity": stock_quantity,
            "featured": featured, "is_active": is_active, "image_url": image_url,
            "created_at": datetime.now().isoformat()
        }
        
        result = insert_table_data("products", product_data)
        return {"message": "Product created successfully", "product": result.data[0]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating product: {str(e)}")

@app.post("/admin/categories")
def create_category(
    name: str = Form(...), description: str = Form(...), 
    icon: str = Form(...), color: str = Form(...),
    display_order: int = Form(1), is_active: bool = Form(True),
    image: Optional[UploadFile] = File(None)
):
    """Create a new category"""
    try:
        image_url = None
        if image and image.filename:
            FileManager.validate_image(image)
            image_url = FileManager.save_file(image, UPLOADS_DIR / "categories")
        
        category_data = {
            "name": name, "description": description, "icon": icon, "color": color,
            "display_order": display_order, "is_active": is_active, "image_url": image_url,
            "created_at": datetime.now().isoformat()
        }
        
        result = insert_table_data("categories", category_data)
        return {"message": "Category created successfully", "category": result.data[0]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating category: {str(e)}")

@app.post("/admin/banners")
def create_banner(
    title: str = Form(...), description: str = Form(""),
    link_url: str = Form(""), is_active: bool = Form(True),
    display_order: int = Form(1), image: Optional[UploadFile] = File(None)
):
    """Create a new banner"""
    try:
        image_url = None
        if image and image.filename:
            FileManager.validate_image(image)
            image_url = FileManager.save_file(image, UPLOADS_DIR / "banners")
        
        banner_data = {
            "title": title, "description": description, "link_url": link_url,
            "is_active": is_active, "display_order": display_order, "image_url": image_url,
            "created_at": datetime.now().isoformat()
        }
        
        result = insert_table_data("banners", banner_data)
        return {"message": "Banner created successfully", "banner": result.data[0]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating banner: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)