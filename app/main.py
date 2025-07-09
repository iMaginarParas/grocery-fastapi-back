# Mobile App Backend - Phone Number + Guest Login
# Enhanced with comprehensive admin panel functionality

import os
import uuid
import shutil
from pathlib import Path
from datetime import datetime, timedelta
import calendar
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Header, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, validator
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import supabase
try:
    from supabase import create_client, Client
    
    SUPABASE_URL = os.getenv("SUPABASE_URL", "https://etxqtocatvqeombnbufk.supabase.co")
    SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImV0eHF0b2NhdHZxZW9tYm5idWZrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTE3NTA4ODUsImV4cCI6MjA2NzMyNjg4NX0.S1bUwbOLJARZAuxFgeALD1mQk59vsIL-Cw_JFqK1_WQ")
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print(f"✅ Connected to Supabase: {SUPABASE_URL}")
except Exception as e:
    print(f"❌ Supabase connection error: {e}")
    supabase = None

app = FastAPI(
    title="Veggie Delivery Mobile App API",
    description="Backend for mobile app with phone login + guest access + Enhanced Admin Panel",
    version="6.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Mobile app access
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# File upload setup
UPLOADS_DIR = Path("uploads")
for directory in [UPLOADS_DIR, UPLOADS_DIR / "products", UPLOADS_DIR / "categories", UPLOADS_DIR / "banners"]:
    directory.mkdir(exist_ok=True)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Pydantic Models for Mobile App

class PhoneLogin(BaseModel):
    """Phone number for app login (no password)"""
    phone: str
    name: Optional[str] = "Guest User"
    
    @validator('phone')
    def validate_phone(cls, v):
        phone_digits = ''.join(filter(str.isdigit, v))
        if len(phone_digits) != 10:
            raise ValueError('Phone must be exactly 10 digits')
        if not phone_digits.startswith(('6', '7', '8', '9')):
            raise ValueError('Invalid Indian phone number')
        return phone_digits

class CartItem(BaseModel):
    """Items in user's cart"""
    product_id: str
    quantity: int = 1
    selected_weight: str = "500g"  # 250g, 500g, 1kg
    
    @validator('quantity')
    def validate_quantity(cls, v):
        if v < 1 or v > 20:
            raise ValueError('Quantity must be between 1 and 20')
        return v

class DeliveryAddress(BaseModel):
    """User's delivery address"""
    name: str
    phone: str
    address_line: str
    landmark: Optional[str] = None
    area: str
    pincode: str
    address_type: str = "home"  # home, office, other
    
    @validator('name')
    def validate_name(cls, v):
        if len(v.strip()) < 2:
            raise ValueError('Name must be at least 2 characters')
        return v.strip()

class OrderCheckout(BaseModel):
    """Order placement"""
    user_phone: str
    delivery_address: DeliveryAddress
    cart_items: List[CartItem]
    delivery_slot: str = "today_evening"  # today_morning, today_evening, tomorrow_morning
    payment_method: str = "cod"  # cod, online
    special_instructions: Optional[str] = None

# Database Helper Functions
def get_table_data(table_name: str, filters: Dict = None, columns: str = "*"):
    """Get data from table with optional filters"""
    try:
        response = supabase.table(table_name).select(columns).execute()
        
        if response.data and filters:
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
        existing_records = get_table_data(table_name, filters)
        
        if existing_records:
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
        if not supabase:
            raise HTTPException(status_code=500, detail="Database not connected")
        
        # Build delete query
        query = supabase.table(table_name).delete()
        
        # Add filters
        for key, value in filters.items():
            query = query.eq(key, value)
        
        response = query.execute()
        return response
    except Exception as e:
        print(f"Delete data error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 📸 SUPABASE STORAGE HELPER FUNCTIONS
def upload_to_supabase_storage(file_content: bytes, bucket: str, file_path: str, content_type: str):
    """Upload file to Supabase Storage"""
    try:
        if not supabase:
            return {"success": False, "error": "Supabase not connected"}
        
        # Check if bucket exists first
        try:
            buckets = supabase.storage.list_buckets()
            bucket_names = [b.get("name") for b in buckets]
            
            if bucket not in bucket_names:
                # Try to create bucket
                supabase.storage.create_bucket(bucket, options={"public": True})
                print(f"✅ Created bucket: {bucket}")
        except Exception as bucket_error:
            print(f"⚠️ Bucket check/creation error: {bucket_error}")
            return {"success": False, "error": f"Bucket issue: {bucket_error}"}
        
        # Upload to Supabase Storage
        result = supabase.storage.from_(bucket).upload(
            file_path, 
            file_content,
            file_options={"content-type": content_type}
        )
        
        # Get public URL
        public_url = supabase.storage.from_(bucket).get_public_url(file_path)
        
        return {
            "success": True,
            "url": public_url,
            "path": file_path
        }
    except Exception as e:
        print(f"Supabase storage upload error: {e}")
        return {
            "success": False,
            "error": str(e)
        }

def delete_from_supabase_storage(bucket: str, file_path: str):
    """Delete file from Supabase Storage"""
    try:
        if not supabase:
            return {"success": False, "error": "Supabase not connected"}
            
        result = supabase.storage.from_(bucket).remove([file_path])
        return {"success": True}
    except Exception as e:
        print(f"Supabase storage delete error: {e}")
        return {"success": False, "error": str(e)}

# Mobile App Endpoints

@app.get("/")
def root():
    """API Information"""
    return {
        "message": "🥬 Veggie Delivery Mobile App API",
        "status": "running",
        "version": "6.0.0",
        "app_flow": "splash → phone_login → home → cart → checkout → orders",
        "features": [
            "phone_number_login",
            "guest_access", 
            "product_search",
            "cart_management",
            "address_management",
            "order_history",
            "delivery_tracking",
            "enhanced_admin_panel"
        ],
        "docs": "http://localhost:8000/docs"
    }

@app.get("/health")
def health_check():
    """Health check for mobile app"""
    try:
        if supabase:
            result = supabase.table("categories").select("id").limit(1).execute()
            return {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "database": "connected",
                "app_ready": True
            }
    except Exception as e:
        return {"status": "database-error", "error": str(e), "app_ready": False}
    
    return {"status": "no-database", "app_ready": False}

# 📱 LOGIN SCREEN APIs

@app.post("/app/login/phone")
def phone_login(login_data: PhoneLogin):
    """Phone number login (no password) - stores user if new"""
    try:
        # Check if user exists
        existing_users = get_table_data("app_users", {"phone": login_data.phone})
        
        if existing_users:
            # Existing user - update last login
            user = existing_users[0]
            update_data = {
                "last_login": datetime.now().isoformat(),
                "login_count": user.get("login_count", 0) + 1
            }
            update_table_data("app_users", update_data, {"phone": login_data.phone})
            
            return {
                "success": True,
                "user_type": "returning",
                "user": {
                    "phone": user["phone"],
                    "name": user.get("name", "User"),
                    "user_id": user["id"],
                    "total_orders": len(get_table_data("mobile_orders", {"user_phone": login_data.phone}))
                },
                "message": f"Welcome back!"
            }
        else:
            # New user - create account
            new_user = {
                "phone": login_data.phone,
                "name": login_data.name or "User",
                "created_at": datetime.now().isoformat(),
                "last_login": datetime.now().isoformat(),
                "login_count": 1,
                "is_active": True
            }
            
            result = insert_table_data("app_users", new_user)
            
            return {
                "success": True,
                "user_type": "new",
                "user": {
                    "phone": login_data.phone,
                    "name": login_data.name or "User",
                    "user_id": result.data[0]["id"] if result.data else None,
                    "total_orders": 0
                },
                "message": "Account created! Welcome to our veggie store!"
            }
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

@app.post("/app/login/guest")
def guest_login():
    """Guest login - no phone required"""
    guest_id = f"guest_{uuid.uuid4().hex[:8]}"
    
    return {
        "success": True,
        "user_type": "guest",
        "user": {
            "phone": None,
            "name": "Guest User",
            "user_id": guest_id,
            "total_orders": 0
        },
        "message": "Welcome! Browse as guest",
        "limitations": ["Cannot save addresses", "Cannot view order history"]
    }

# 🏠 HOME SCREEN APIs

@app.get("/app/home")
def get_home_screen_data():
    """Get all data for home screen"""
    try:
        # Get banners for top carousel
        banners = get_table_data("banners", {"is_active": True})
        sorted_banners = sorted(banners, key=lambda x: x.get("display_order", 0))
        
        # Get categories for navigation
        categories = get_table_data("categories", {"is_active": True})
        sorted_categories = sorted(categories, key=lambda x: x.get("display_order", 0))
        
        # Get featured products
        featured_products = get_table_data("products", {"is_active": True, "featured": True})
        
        # Get all products (for search)
        all_products = get_table_data("products", {"is_active": True})
        
        return {
            "banners": sorted_banners,
            "categories": sorted_categories,
            "featured_products": featured_products,
            "total_products": len(all_products),
            "app_info": {
                "free_delivery_above": 199,
                "delivery_charge": 40,
                "delivery_slots": ["today_morning", "today_evening", "tomorrow_morning"],
                "payment_methods": ["cod", "online"]
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading home screen: {str(e)}")

@app.get("/app/categories")
def get_categories():
    """Get all categories for navigation"""
    try:
        categories = get_table_data("categories", {"is_active": True})
        return sorted(categories, key=lambda x: x.get("display_order", 0))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching categories: {str(e)}")

@app.get("/app/banners")
def get_banners():
    """Get banners for home screen carousel"""
    try:
        banners = get_table_data("banners", {"is_active": True})
        return sorted(banners, key=lambda x: x.get("display_order", 0))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching banners: {str(e)}")

# 🔍 PRODUCT SEARCH & BROWSING APIs

@app.get("/app/products")
def get_products(
    category_id: Optional[str] = None,
    search: Optional[str] = None,
    featured: Optional[bool] = None,
    sort_by: str = "name",  # name, price_low, price_high, popular
    skip: int = 0,
    limit: int = 50
):
    """Get products with search and filters"""
    try:
        # Get all active products
        products = get_table_data("products", {"is_active": True})
        
        # Apply category filter
        if category_id:
            products = [p for p in products if p.get("category_id") == category_id]
        
        # Apply featured filter
        if featured is not None:
            products = [p for p in products if p.get("featured", False) == featured]
        
        # Apply search filter
        if search:
            search_lower = search.lower()
            products = [
                p for p in products 
                if (search_lower in p["name"].lower() or 
                    search_lower in p.get("description", "").lower())
            ]
        
        # Apply sorting
        if sort_by == "price_low":
            products = sorted(products, key=lambda x: x.get("base_price", 0))
        elif sort_by == "price_high":
            products = sorted(products, key=lambda x: x.get("base_price", 0), reverse=True)
        elif sort_by == "popular":
            products = sorted(products, key=lambda x: x.get("featured", False), reverse=True)
        else:  # name
            products = sorted(products, key=lambda x: x.get("name", ""))
        
        # Add category info to each product
        categories = get_table_data("categories")
        for product in products:
            category = next((c for c in categories if c["id"] == product["category_id"]), None)
            if category:
                product["category_name"] = category["name"]
                product["category_icon"] = category.get("icon", "🥬")
        
        # Pagination
        paginated_products = products[skip:skip + limit]
        
        return {
            "products": paginated_products,
            "total_count": len(products),
            "has_more": (skip + limit) < len(products),
            "filters_applied": {
                "category_id": category_id,
                "search": search,
                "featured": featured,
                "sort_by": sort_by
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching products: {str(e)}")

@app.get("/app/products/{product_id}")
def get_product_details(product_id: str):
    """Get detailed product information"""
    try:
        products = get_table_data("products", {"id": product_id, "is_active": True})
        if not products:
            raise HTTPException(status_code=404, detail="Product not found")
        
        product = products[0]
        
        # Add category info
        categories = get_table_data("categories")
        category = next((c for c in categories if c["id"] == product["category_id"]), None)
        if category:
            product["category"] = category
        
        # Add stock status
        stock = product.get("stock_quantity", 0)
        product["stock_status"] = (
            "in_stock" if stock > 10 else
            "low_stock" if stock > 0 else
            "out_of_stock"
        )
        
        return product
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching product: {str(e)}")

@app.get("/app/search")
def search_products(q: str, limit: int = 10):
    """Quick search for products"""
    try:
        if len(q.strip()) < 2:
            return {"products": [], "message": "Search query too short"}
        
        products = get_table_data("products", {"is_active": True})
        search_lower = q.lower()
        
        # Search in name and description
        matching_products = [
            p for p in products 
            if (search_lower in p["name"].lower() or 
                search_lower in p.get("description", "").lower())
        ]
        
        # Sort by relevance (name matches first)
        name_matches = [p for p in matching_products if search_lower in p["name"].lower()]
        desc_matches = [p for p in matching_products if search_lower not in p["name"].lower()]
        
        sorted_results = name_matches + desc_matches
        
        return {
            "products": sorted_results[:limit],
            "total_found": len(matching_products),
            "search_query": q
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

# 🛒 CART MANAGEMENT APIs

@app.post("/app/cart/add")
def add_to_cart(item: CartItem, user_phone: Optional[str] = Header(None)):
    """Add item to cart (guest or logged-in user)"""
    try:
        # Validate product exists and has stock
        products = get_table_data("products", {"id": item.product_id})
        if not products:
            raise HTTPException(status_code=404, detail="Product not found")
        
        product = products[0]
        if product["stock_quantity"] < item.quantity:
            raise HTTPException(status_code=400, detail=f"Only {product['stock_quantity']} items available")
        
        cart_id = user_phone or f"guest_{uuid.uuid4().hex[:8]}"
        
        # Check if item already in cart
        existing_items = get_table_data("mobile_cart", {
            "cart_id": cart_id,
            "product_id": item.product_id,
            "selected_weight": item.selected_weight
        })
        
        if existing_items:
            # Update quantity
            existing_item = existing_items[0]
            new_quantity = existing_item["quantity"] + item.quantity
            
            if new_quantity > product["stock_quantity"]:
                raise HTTPException(status_code=400, detail="Not enough stock available")
            
            update_data = {
                "quantity": new_quantity,
                "updated_at": datetime.now().isoformat()
            }
            update_table_data("mobile_cart", update_data, {"id": existing_item["id"]})
            
            return {"message": "Cart updated", "quantity": new_quantity}
        else:
            # Add new item
            cart_item = {
                "cart_id": cart_id,
                "product_id": item.product_id,
                "quantity": item.quantity,
                "selected_weight": item.selected_weight,
                "added_at": datetime.now().isoformat()
            }
            
            result = insert_table_data("mobile_cart", cart_item)
            return {"message": "Added to cart", "cart_item": result.data[0] if result.data else None}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding to cart: {str(e)}")

@app.get("/app/cart")
def get_cart(user_phone: Optional[str] = Header(None), guest_id: Optional[str] = Header(None)):
    """Get cart contents with cost breakdown"""
    try:
        cart_id = user_phone or guest_id
        if not cart_id:
            return {"items": [], "total": 0, "message": "No cart ID provided"}
        
        # Get cart items
        cart_items = get_table_data("mobile_cart", {"cart_id": cart_id})
        
        if not cart_items:
            return {
                "items": [],
                "subtotal": 0,
                "delivery_charge": 40,
                "total": 40,
                "free_delivery_remaining": 199,
                "message": "Cart is empty"
            }
        
        # Calculate costs
        enriched_items = []
        subtotal = 0
        
        products = get_table_data("products")
        
        for cart_item in cart_items:
            product = next((p for p in products if p["id"] == cart_item["product_id"]), None)
            if product:
                unit_price = product["base_price"]
                item_total = unit_price * cart_item["quantity"]
                subtotal += item_total
                
                enriched_items.append({
                    "cart_item_id": cart_item["id"],
                    "product": {
                        "id": product["id"],
                        "name": product["name"],
                        "image_url": product.get("image_url"),
                        "base_price": unit_price
                    },
                    "quantity": cart_item["quantity"],
                    "selected_weight": cart_item["selected_weight"],
                    "unit_price": unit_price,
                    "item_total": item_total,
                    "max_quantity": product["stock_quantity"]
                })
        
        # Calculate delivery
        delivery_charge = 0 if subtotal >= 199 else 40
        total = subtotal + delivery_charge
        free_delivery_remaining = max(0, 199 - subtotal)
        
        return {
            "items": enriched_items,
            "subtotal": subtotal,
            "delivery_charge": delivery_charge,
            "total": total,
            "free_delivery_remaining": free_delivery_remaining,
            "item_count": len(enriched_items)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching cart: {str(e)}")

@app.put("/app/cart/{cart_item_id}")
def update_cart_item(cart_item_id: str, quantity: int):
    """Update cart item quantity"""
    try:
        if quantity <= 0:
            # Remove item
            supabase.table("mobile_cart").delete().eq("id", cart_item_id).execute()
            return {"message": "Item removed from cart"}
        
        # Get cart item and product
        cart_items = get_table_data("mobile_cart", {"id": cart_item_id})
        if not cart_items:
            raise HTTPException(status_code=404, detail="Cart item not found")
        
        cart_item = cart_items[0]
        products = get_table_data("products", {"id": cart_item["product_id"]})
        
        if not products:
            raise HTTPException(status_code=404, detail="Product not found")
        
        product = products[0]
        if quantity > product["stock_quantity"]:
            raise HTTPException(status_code=400, detail=f"Only {product['stock_quantity']} items available")
        
        # Update quantity
        update_data = {
            "quantity": quantity,
            "updated_at": datetime.now().isoformat()
        }
        update_table_data("mobile_cart", update_data, {"id": cart_item_id})
        
        return {"message": "Cart updated", "new_quantity": quantity}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating cart: {str(e)}")

@app.delete("/app/cart/{cart_item_id}")
def remove_cart_item(cart_item_id: str):
    """Remove item from cart"""
    try:
        supabase.table("mobile_cart").delete().eq("id", cart_item_id).execute()
        return {"message": "Item removed from cart"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error removing item: {str(e)}")

@app.delete("/app/cart")
def clear_cart(user_phone: Optional[str] = Header(None), guest_id: Optional[str] = Header(None)):
    """Clear entire cart"""
    try:
        cart_id = user_phone or guest_id
        if not cart_id:
            raise HTTPException(status_code=400, detail="No cart ID provided")
        
        supabase.table("mobile_cart").delete().eq("cart_id", cart_id).execute()
        return {"message": "Cart cleared"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing cart: {str(e)}")

# 🚚 CHECKOUT & ORDER APIs

@app.post("/app/checkout")
def place_order(order: OrderCheckout):
    """Place order from mobile app"""
    try:
        if not order.cart_items:
            raise HTTPException(status_code=400, detail="Cart is empty")
        
        # Calculate order totals
        subtotal = 0
        order_items = []
        products = get_table_data("products")
        
        for cart_item in order.cart_items:
            product = next((p for p in products if p["id"] == cart_item.product_id), None)
            if not product:
                raise HTTPException(status_code=404, detail=f"Product {cart_item.product_id} not found")
            
            if product["stock_quantity"] < cart_item.quantity:
                raise HTTPException(status_code=400, detail=f"Insufficient stock for {product['name']}")
            
            unit_price = product["base_price"]
            item_total = unit_price * cart_item.quantity
            subtotal += item_total
            
            order_items.append({
                "product_id": cart_item.product_id,
                "product_name": product["name"],
                "quantity": cart_item.quantity,
                "selected_weight": cart_item.selected_weight,
                "unit_price": unit_price,
                "item_total": item_total
            })
        
        # Calculate final amounts
        delivery_charge = 0 if subtotal >= 199 else 40
        total_amount = subtotal + delivery_charge
        
        # Generate order number
        existing_orders = get_table_data("mobile_orders")
        order_number = f"VEG{len(existing_orders) + 1:04d}"
        
        # Create order
        mobile_order = {
            "order_number": order_number,
            "user_phone": order.user_phone,
            "customer_name": order.delivery_address.name,
            "delivery_address": order.delivery_address.dict(),
            "subtotal": subtotal,
            "delivery_charge": delivery_charge,
            "total_amount": total_amount,
            "delivery_slot": order.delivery_slot,
            "payment_method": order.payment_method,
            "special_instructions": order.special_instructions,
            "status": "placed",
            "items": order_items,
            "created_at": datetime.now().isoformat()
        }
        
        # Insert order
        result = insert_table_data("mobile_orders", mobile_order)
        
        # Clear cart
        if order.user_phone:
            supabase.table("mobile_cart").delete().eq("cart_id", order.user_phone).execute()
        
        # Update stock (simplified - would need proper update function)
        for item in order_items:
            print(f"📦 Reducing stock for {item['product_name']} by {item['quantity']}")
        
        return {
            "success": True,
            "order_id": result.data[0]["id"] if result.data else None,
            "order_number": order_number,
            "total_amount": total_amount,
            "estimated_delivery": "30-60 minutes",
            "message": "Order placed successfully! We'll call you with updates."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error placing order: {str(e)}")

# 📋 ORDER HISTORY APIs

@app.get("/app/orders/{user_phone}")
def get_order_history(user_phone: str):
    """Get order history for user"""
    try:
        # Validate phone
        phone_digits = ''.join(filter(str.isdigit, user_phone))
        if len(phone_digits) != 10:
            raise HTTPException(status_code=400, detail="Invalid phone number")
        
        orders = get_table_data("mobile_orders", {"user_phone": phone_digits})
        
        # Sort by date (newest first)
        sorted_orders = sorted(orders, key=lambda x: x.get("created_at", ""), reverse=True)
        
        # Add status info
        for order in sorted_orders:
            status = order.get("status", "placed")
            order["status_info"] = {
                "placed": {"message": "Order received", "color": "blue"},
                "confirmed": {"message": "Order confirmed", "color": "orange"},
                "preparing": {"message": "Preparing your order", "color": "yellow"},
                "out_for_delivery": {"message": "Out for delivery", "color": "purple"},
                "delivered": {"message": "Delivered", "color": "green"},
                "cancelled": {"message": "Cancelled", "color": "red"}
            }.get(status, {"message": "Unknown status", "color": "gray"})
        
        return {
            "phone": phone_digits,
            "total_orders": len(sorted_orders),
            "orders": sorted_orders
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching orders: {str(e)}")

@app.get("/app/orders/track/{order_number}")
def track_order(order_number: str):
    """Track specific order by order number"""
    try:
        orders = get_table_data("mobile_orders", {"order_number": order_number})
        
        if not orders:
            raise HTTPException(status_code=404, detail="Order not found")
        
        order = orders[0]
        
        # Add tracking timeline
        status = order.get("status", "placed")
        timeline = [
            {"step": "placed", "title": "Order Placed", "completed": True},
            {"step": "confirmed", "title": "Order Confirmed", "completed": status in ["confirmed", "preparing", "out_for_delivery", "delivered"]},
            {"step": "preparing", "title": "Preparing", "completed": status in ["preparing", "out_for_delivery", "delivered"]},
            {"step": "out_for_delivery", "title": "Out for Delivery", "completed": status in ["out_for_delivery", "delivered"]},
            {"step": "delivered", "title": "Delivered", "completed": status == "delivered"}
        ]
        
        order["tracking_timeline"] = timeline
        
        return order
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error tracking order: {str(e)}")

# 👨‍💼 ADMIN APIs for Store Owner

@app.get("/admin/dashboard")
def get_admin_dashboard():
    """Admin dashboard for mobile app orders"""
    try:
        orders = get_table_data("mobile_orders")
        products = get_table_data("products")
        users = get_table_data("app_users")
        
        # Today's data
        today = datetime.now().date().isoformat()
        today_orders = [o for o in orders if o.get("created_at", "").startswith(today)]
        
        # Revenue calculations
        total_revenue = sum(order.get("total_amount", 0) for order in orders)
        today_revenue = sum(order.get("total_amount", 0) for order in today_orders)
        
        # Order status breakdown
        status_breakdown = {}
        for order in orders:
            status = order.get("status", "placed")
            status_breakdown[status] = status_breakdown.get(status, 0) + 1
        
        # Popular products
        product_sales = {}
        for order in orders:
            for item in order.get("items", []):
                product_id = item.get("product_id")
                product_sales[product_id] = product_sales.get(product_id, 0) + item.get("quantity", 0)
        
        # Get top 5 products
        top_products = []
        for product_id, quantity in sorted(product_sales.items(), key=lambda x: x[1], reverse=True)[:5]:
            product = next((p for p in products if p["id"] == product_id), None)
            if product:
                top_products.append({
                    "product": product,
                    "total_sold": quantity
                })
        
        return {
            "overview": {
                "total_orders": len(orders),
                "today_orders": len(today_orders),
                "total_revenue": total_revenue,
                "today_revenue": today_revenue,
                "total_customers": len(users),
                "active_products": len([p for p in products if p.get("is_active", True)])
            },
            "order_status": status_breakdown,
            "top_products": top_products,
            "low_stock_alerts": [
                p for p in products 
                if p.get("stock_quantity", 0) < 5 and p.get("is_active", True)
            ]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading dashboard: {str(e)}")

@app.get("/admin/orders")
def get_all_mobile_orders():
    """Get all orders for admin"""
    try:
        orders = get_table_data("mobile_orders")
        
        # Sort by date (newest first)
        sorted_orders = sorted(orders, key=lambda x: x.get("created_at", ""), reverse=True)
        
        return {
            "orders": sorted_orders,
            "total_count": len(sorted_orders)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching orders: {str(e)}")

@app.put("/admin/orders/{order_id}/status")
def update_order_status_admin(order_id: str, status_data: dict):
    """Update order status from admin"""
    try:
        new_status = status_data.get("status")
        valid_statuses = ["placed", "confirmed", "preparing", "out_for_delivery", "delivered", "cancelled"]
        
        if new_status not in valid_statuses:
            raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")
        
        update_data = {
            "status": new_status,
            "updated_at": datetime.now().isoformat()
        }
        
        result = update_table_data("mobile_orders", update_data, {"id": order_id})
        
        if result:
            return {"message": f"Order status updated to {new_status}"}
        else:
            raise HTTPException(status_code=404, detail="Order not found")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating order: {str(e)}")

# 💰 FINANCIAL REPORTS & ANALYTICS

@app.get("/admin/reports/revenue")
def get_revenue_report(
    period: str = "month",  # day, week, month, year
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """Detailed revenue reports"""
    try:
        orders = get_table_data("mobile_orders")
        
        # Filter by date range
        if start_date and end_date:
            filtered_orders = [
                o for o in orders 
                if start_date <= o.get("created_at", "")[:10] <= end_date
            ]
        else:
            # Default periods
            now = datetime.now()
            if period == "day":
                start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                filtered_orders = [
                    o for o in orders 
                    if o.get("created_at", "").startswith(start.date().isoformat())
                ]
            elif period == "week":
                start = now - timedelta(days=7)
                filtered_orders = [
                    o for o in orders 
                    if o.get("created_at", "") >= start.isoformat()
                ]
            elif period == "month":
                start = now.replace(day=1)
                filtered_orders = [
                    o for o in orders 
                    if o.get("created_at", "")[:7] == start.strftime("%Y-%m")
                ]
            else:  # year
                start = now.replace(month=1, day=1)
                filtered_orders = [
                    o for o in orders 
                    if o.get("created_at", "")[:4] == str(start.year)
                ]
        
        # Calculate metrics
        total_revenue = sum(o.get("total_amount", 0) for o in filtered_orders)
        total_orders = len(filtered_orders)
        avg_order_value = total_revenue / total_orders if total_orders > 0 else 0
        
        # Payment method breakdown
        payment_breakdown = {}
        for order in filtered_orders:
            method = order.get("payment_method", "cod")
            payment_breakdown[method] = payment_breakdown.get(method, 0) + order.get("total_amount", 0)
        
        # Daily breakdown for charts
        daily_revenue = {}
        for order in filtered_orders:
            date = order.get("created_at", "")[:10]
            daily_revenue[date] = daily_revenue.get(date, 0) + order.get("total_amount", 0)
        
        # Status breakdown
        status_revenue = {}
        for order in filtered_orders:
            status = order.get("status", "placed")
            status_revenue[status] = status_revenue.get(status, 0) + order.get("total_amount", 0)
        
        return {
            "period": period,
            "summary": {
                "total_revenue": total_revenue,
                "total_orders": total_orders,
                "average_order_value": round(avg_order_value, 2),
                "delivery_revenue": sum(o.get("delivery_charge", 0) for o in filtered_orders)
            },
            "payment_methods": payment_breakdown,
            "daily_breakdown": daily_revenue,
            "order_status": status_revenue,
            "top_revenue_days": sorted(daily_revenue.items(), key=lambda x: x[1], reverse=True)[:7]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating revenue report: {str(e)}")

@app.get("/admin/analytics/products")
def get_product_analytics():
    """Product performance analytics"""
    try:
        orders = get_table_data("mobile_orders")
        products = get_table_data("products")
        
        # Product sales analysis
        product_metrics = {}
        
        for order in orders:
            for item in order.get("items", []):
                product_id = item.get("product_id")
                if product_id not in product_metrics:
                    product_metrics[product_id] = {
                        "total_quantity": 0,
                        "total_revenue": 0,
                        "order_count": 0
                    }
                
                product_metrics[product_id]["total_quantity"] += item.get("quantity", 0)
                product_metrics[product_id]["total_revenue"] += item.get("item_total", 0)
                product_metrics[product_id]["order_count"] += 1
        
        # Enrich with product details
        enriched_metrics = []
        for product_id, metrics in product_metrics.items():
            product = next((p for p in products if p["id"] == product_id), None)
            if product:
                enriched_metrics.append({
                    "product": product,
                    "metrics": {
                        **metrics,
                        "avg_quantity_per_order": metrics["total_quantity"] / metrics["order_count"] if metrics["order_count"] > 0 else 0,
                        "revenue_per_unit": metrics["total_revenue"] / metrics["total_quantity"] if metrics["total_quantity"] > 0 else 0
                    }
                })
        
        # Sort by different criteria
        top_by_quantity = sorted(enriched_metrics, key=lambda x: x["metrics"]["total_quantity"], reverse=True)[:10]
        top_by_revenue = sorted(enriched_metrics, key=lambda x: x["metrics"]["total_revenue"], reverse=True)[:10]
        top_by_orders = sorted(enriched_metrics, key=lambda x: x["metrics"]["order_count"], reverse=True)[:10]
        
        # Low performing products
        low_performers = [
            p for p in products 
            if p["id"] not in product_metrics and p.get("is_active", True)
        ]
        
        return {
            "top_selling_by_quantity": top_by_quantity,
            "top_revenue_generators": top_by_revenue,
            "most_frequently_ordered": top_by_orders,
            "low_performers": low_performers,
            "total_products_sold": len(product_metrics),
            "products_never_sold": len(low_performers)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating product analytics: {str(e)}")

# 👥 CUSTOMER MANAGEMENT

@app.get("/admin/customers")
def get_all_customers():
    """Complete customer management"""
    try:
        users = get_table_data("app_users")
        orders = get_table_data("mobile_orders")
        
        # Enrich users with order data
        enriched_customers = []
        
        for user in users:
            user_orders = [o for o in orders if o.get("user_phone") == user["phone"]]
            
            total_spent = sum(o.get("total_amount", 0) for o in user_orders)
            avg_order_value = total_spent / len(user_orders) if user_orders else 0
            
            # Last order date
            last_order = None
            if user_orders:
                last_order = max(user_orders, key=lambda x: x.get("created_at", ""))
            
            # Customer segments
            if len(user_orders) == 0:
                segment = "new"
            elif len(user_orders) == 1:
                segment = "one_time"
            elif len(user_orders) < 5:
                segment = "occasional"
            elif len(user_orders) < 10:
                segment = "regular"
            else:
                segment = "loyal"
            
            enriched_customers.append({
                "user": user,
                "order_stats": {
                    "total_orders": len(user_orders),
                    "total_spent": total_spent,
                    "average_order_value": round(avg_order_value, 2),
                    "last_order_date": last_order.get("created_at") if last_order else None,
                    "last_order_amount": last_order.get("total_amount") if last_order else 0
                },
                "segment": segment,
                "status": "active" if user.get("is_active", True) else "inactive"
            })
        
        # Sort by total spent (VIP customers first)
        sorted_customers = sorted(enriched_customers, key=lambda x: x["order_stats"]["total_spent"], reverse=True)
        
        # Customer segments summary
        segment_summary = {}
        for customer in enriched_customers:
            segment = customer["segment"]
            segment_summary[segment] = segment_summary.get(segment, 0) + 1
        
        return {
            "customers": sorted_customers,
            "summary": {
                "total_customers": len(enriched_customers),
                "active_customers": len([c for c in enriched_customers if c["status"] == "active"]),
                "segments": segment_summary,
                "vip_customers": len([c for c in enriched_customers if c["order_stats"]["total_spent"] > 1000])
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching customers: {str(e)}")

@app.get("/admin/customers/{phone}/details")
def get_customer_details(phone: str):
    """Detailed customer profile"""
    try:
        # Get user info
        users = get_table_data("app_users", {"phone": phone})
        if not users:
            raise HTTPException(status_code=404, detail="Customer not found")
        
        user = users[0]
        
        # Get customer's orders
        orders = get_table_data("mobile_orders", {"user_phone": phone})
        
        # Get saved addresses
        addresses = get_table_data("user_addresses", {"user_phone": phone})
        
        # Calculate customer metrics
        total_spent = sum(o.get("total_amount", 0) for o in orders)
        avg_order_value = total_spent / len(orders) if orders else 0
        
        # Order frequency
        if len(orders) > 1:
            first_order = min(orders, key=lambda x: x.get("created_at", ""))
            last_order = max(orders, key=lambda x: x.get("created_at", ""))
            
            first_date = datetime.fromisoformat(first_order["created_at"].replace("Z", "+00:00"))
            last_date = datetime.fromisoformat(last_order["created_at"].replace("Z", "+00:00"))
            
            days_between = (last_date - first_date).days
            order_frequency = days_between / len(orders) if len(orders) > 1 else 0
        else:
            order_frequency = 0
        
        # Favorite products
        product_counts = {}
        for order in orders:
            for item in order.get("items", []):
                product_id = item.get("product_id")
                product_counts[product_id] = product_counts.get(product_id, 0) + item.get("quantity", 0)
        
        # Get top 5 favorite products
        products = get_table_data("products")
        favorite_products = []
        for product_id, quantity in sorted(product_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
            product = next((p for p in products if p["id"] == product_id), None)
            if product:
                favorite_products.append({
                    "product": product,
                    "total_ordered": quantity
                })
        
        return {
            "customer": user,
            "order_history": sorted(orders, key=lambda x: x.get("created_at", ""), reverse=True),
            "saved_addresses": addresses,
            "analytics": {
                "total_orders": len(orders),
                "total_spent": total_spent,
                "average_order_value": round(avg_order_value, 2),
                "order_frequency_days": round(order_frequency, 1),
                "favorite_products": favorite_products
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching customer details: {str(e)}")

# 📦 ADVANCED INVENTORY MANAGEMENT

@app.get("/admin/inventory")
def get_inventory_status():
    """Complete inventory management"""
    try:
        products = get_table_data("products")
        orders = get_table_data("mobile_orders")
        
        # Calculate inventory metrics
        inventory_data = []
        
        for product in products:
            # Calculate sales velocity (items sold per day)
            product_sales = []
            for order in orders:
                for item in order.get("items", []):
                    if item.get("product_id") == product["id"]:
                        product_sales.append({
                            "quantity": item.get("quantity", 0),
                            "date": order.get("created_at", "")[:10]
                        })
            
            # Daily sales average (last 30 days)
            recent_sales = [s for s in product_sales if s["date"] >= (datetime.now() - timedelta(days=30)).date().isoformat()]
            daily_avg = sum(s["quantity"] for s in recent_sales) / 30 if recent_sales else 0
            
            # Days until stock out
            current_stock = product.get("stock_quantity", 0)
            days_until_stockout = current_stock / daily_avg if daily_avg > 0 else float('inf')
            
            # Stock status
            if current_stock == 0:
                status = "out_of_stock"
            elif current_stock < 5:
                status = "critical"
            elif days_until_stockout < 7:
                status = "low"
            elif days_until_stockout < 14:
                status = "medium"
            else:
                status = "good"
            
            inventory_data.append({
                "product": product,
                "stock_info": {
                    "current_stock": current_stock,
                    "daily_sales_avg": round(daily_avg, 2),
                    "days_until_stockout": round(days_until_stockout, 1) if days_until_stockout != float('inf') else None,
                    "status": status,
                    "total_sold": sum(s["quantity"] for s in product_sales),
                    "reorder_suggested": status in ["critical", "low"]
                }
            })
        
        # Sort by urgency
        sorted_inventory = sorted(inventory_data, key=lambda x: (
            0 if x["stock_info"]["status"] == "out_of_stock" else
            1 if x["stock_info"]["status"] == "critical" else
            2 if x["stock_info"]["status"] == "low" else
            3
        ))
        
        # Summary stats
        status_counts = {}
        for item in inventory_data:
            status = item["stock_info"]["status"]
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return {
            "inventory": sorted_inventory,
            "summary": {
                "total_products": len(products),
                "status_breakdown": status_counts,
                "reorder_needed": len([i for i in inventory_data if i["stock_info"]["reorder_suggested"]]),
                "out_of_stock": status_counts.get("out_of_stock", 0),
                "critical_stock": status_counts.get("critical", 0)
            },
            "alerts": [
                i for i in sorted_inventory 
                if i["stock_info"]["status"] in ["out_of_stock", "critical", "low"]
            ]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching inventory: {str(e)}")

@app.put("/admin/inventory/{product_id}/stock")
def update_stock(product_id: str, stock_data: dict):
    """Update product stock"""
    try:
        new_stock = stock_data.get("stock_quantity")
        if new_stock is None or new_stock < 0:
            raise HTTPException(status_code=400, detail="Valid stock quantity required")
        
        update_data = {
            "stock_quantity": new_stock,
            "updated_at": datetime.now().isoformat()
        }
        
        result = update_table_data("products", update_data, {"id": product_id})
        
        if result:
            return {"message": f"Stock updated to {new_stock}", "new_stock": new_stock}
        else:
            raise HTTPException(status_code=404, detail="Product not found")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating stock: {str(e)}")

# ⚙️ BUSINESS SETTINGS

@app.get("/admin/settings")
def get_business_settings():
    """Get business configuration"""
    return {
        "business_info": {
            "name": "Fresh Veggie Store",
            "phone": "+91-98765-43210",
            "email": "orders@freshveggies.com",
            "address": "Local Vegetable Market, Sector 15",
            "working_hours": {
                "monday": {"open": "07:00", "close": "21:00"},
                "tuesday": {"open": "07:00", "close": "21:00"},
                "wednesday": {"open": "07:00", "close": "21:00"},
                "thursday": {"open": "07:00", "close": "21:00"},
                "friday": {"open": "07:00", "close": "21:00"},
                "saturday": {"open": "07:00", "close": "21:00"},
                "sunday": {"open": "08:00", "close": "20:00"}
            }
        },
        "delivery_settings": {
            "free_delivery_threshold": 199,
            "delivery_charge": 40,
            "delivery_areas": [
                "Sector 1", "Sector 2", "Sector 3", 
                "MG Road", "Park Street", "City Center"
            ],
            "delivery_slots": [
                {"id": "morning", "label": "Morning", "time": "8:00 AM - 12:00 PM"},
                {"id": "evening", "label": "Evening", "time": "4:00 PM - 8:00 PM"}
            ],
            "estimated_delivery_time": "30-60 minutes"
        },
        "payment_settings": {
            "cod_enabled": True,
            "online_payment_enabled": False,
            "upi_enabled": False
        },
        "app_settings": {
            "guest_checkout_enabled": True,
            "minimum_order_amount": 50,
            "max_items_per_order": 50
        }
    }

@app.put("/admin/settings")
def update_business_settings(settings: dict):
    """Update business settings"""
    try:
        # In a real app, you'd save this to a settings table
        # For now, just return success
        return {
            "message": "Settings updated successfully",
            "updated_at": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating settings: {str(e)}")

# 📊 DELIVERY ANALYTICS

@app.get("/admin/delivery/analytics")
def get_delivery_analytics():
    """Delivery performance analytics"""
    try:
        orders = get_table_data("mobile_orders")
        
        # Delivery slot analysis
        slot_analysis = {}
        for order in orders:
            slot = order.get("delivery_slot", "unknown")
            if slot not in slot_analysis:
                slot_analysis[slot] = {"count": 0, "revenue": 0}
            slot_analysis[slot]["count"] += 1
            slot_analysis[slot]["revenue"] += order.get("total_amount", 0)
        
        # Area analysis from delivery addresses
        area_analysis = {}
        for order in orders:
            address = order.get("delivery_address", {})
            area = address.get("area", "Unknown") if isinstance(address, dict) else "Unknown"
            if area not in area_analysis:
                area_analysis[area] = {"count": 0, "revenue": 0}
            area_analysis[area]["count"] += 1
            area_analysis[area]["revenue"] += order.get("total_amount", 0)
        
        # Delivery charge analysis
        total_delivery_revenue = sum(o.get("delivery_charge", 0) for o in orders)
        free_deliveries = len([o for o in orders if o.get("delivery_charge", 0) == 0])
        paid_deliveries = len(orders) - free_deliveries
        
        return {
            "delivery_slots": slot_analysis,
            "delivery_areas": area_analysis,
            "delivery_charges": {
                "total_delivery_revenue": total_delivery_revenue,
                "free_deliveries": free_deliveries,
                "paid_deliveries": paid_deliveries,
                "avg_delivery_charge": total_delivery_revenue / paid_deliveries if paid_deliveries > 0 else 0
            },
            "top_delivery_areas": sorted(area_analysis.items(), key=lambda x: x[1]["count"], reverse=True)[:5]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating delivery analytics: {str(e)}")

# 🏷️ CATEGORY MANAGEMENT APIs

class CategoryCreate(BaseModel):
    """Create new category"""
    name: str
    description: Optional[str] = ""
    icon: str = "🥬"
    color: str = "#4CAF50"
    display_order: int = 1
    is_active: bool = True

@app.get("/admin/categories")
def get_admin_categories():
    """Get all categories for admin management"""
    try:
        categories = get_table_data("categories")
        return {
            "categories": sorted(categories, key=lambda x: x.get("display_order", 0)),
            "total_count": len(categories)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching categories: {str(e)}")

@app.post("/admin/categories")
def create_category(category: CategoryCreate):
    """Create new category"""
    try:
        category_data = {
            **category.dict(),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        result = insert_table_data("categories", category_data)
        return {
            "message": "Category created successfully",
            "category": result.data[0] if result.data else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating category: {str(e)}")

@app.put("/admin/categories/{category_id}")
def update_category(category_id: str, category_data: dict):
    """Update category"""
    try:
        update_data = {
            **category_data,
            "updated_at": datetime.now().isoformat()
        }
        
        result = update_table_data("categories", update_data, {"id": category_id})
        
        if result:
            return {"message": "Category updated successfully"}
        else:
            raise HTTPException(status_code=404, detail="Category not found")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating category: {str(e)}")

@app.delete("/admin/categories/{category_id}")
def delete_category(category_id: str):
    """Delete category"""
    try:
        if not supabase:
            raise HTTPException(status_code=500, detail="Database not connected")
        
        # Check if category exists
        categories = get_table_data("categories", {"id": category_id})
        if not categories:
            raise HTTPException(status_code=404, detail="Category not found")
        
        # Check if category has products
        products = get_table_data("products", {"category_id": category_id})
        if products:
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot delete category. {len(products)} products are using this category."
            )
        
        # Delete category image if exists
        category = categories[0]
        if category.get("image_url") and category["image_url"].startswith("/uploads/"):
            try:
                file_path = Path(category["image_url"][1:])  # Remove leading slash
                file_path.unlink(missing_ok=True)
            except Exception as e:
                print(f"Error deleting category image: {e}")
        
        # Delete category from database
        delete_table_data("categories", {"id": category_id})
        return {"message": "Category deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Delete category error: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting category: {str(e)}")

# 🛍️ PRODUCT MANAGEMENT APIs

class ProductCreate(BaseModel):
    """Create new product"""
    name: str
    description: str
    category_id: str
    base_price: float
    stock_quantity: int = 0
    featured: bool = False
    is_active: bool = True
    weight_options: List[str] = ["250g", "500g", "1kg"]
    unit_options: List[int] = [1, 2, 3, 4, 5]
    discount_percentage: float = 0.0

@app.get("/admin/products")
def get_admin_products():
    """Get all products for admin management"""
    try:
        products = get_table_data("products")
        categories = get_table_data("categories")
        
        # Enrich products with category info
        for product in products:
            category = next((c for c in categories if c["id"] == product["category_id"]), None)
            if category:
                product["category"] = category
        
        return {
            "products": sorted(products, key=lambda x: x.get("created_at", ""), reverse=True),
            "total_count": len(products)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching products: {str(e)}")

@app.post("/admin/products")
def create_product(product: ProductCreate):
    """Create new product"""
    try:
        # Validate category exists
        categories = get_table_data("categories", {"id": product.category_id})
        if not categories:
            raise HTTPException(status_code=400, detail="Category not found")
        
        product_data = {
            **product.dict(),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        result = insert_table_data("products", product_data)
        return {
            "message": "Product created successfully",
            "product": result.data[0] if result.data else None
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating product: {str(e)}")

@app.put("/admin/products/{product_id}")
def update_product(product_id: str, product_data: dict):
    """Update product"""
    try:
        # If category_id is being updated, validate it exists
        if "category_id" in product_data:
            categories = get_table_data("categories", {"id": product_data["category_id"]})
            if not categories:
                raise HTTPException(status_code=400, detail="Category not found")
        
        update_data = {
            **product_data,
            "updated_at": datetime.now().isoformat()
        }
        
        result = update_table_data("products", update_data, {"id": product_id})
        
        if result:
            return {"message": "Product updated successfully"}
        else:
            raise HTTPException(status_code=404, detail="Product not found")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating product: {str(e)}")

@app.delete("/admin/products/{product_id}")
def delete_product(product_id: str):
    """Delete product"""
    try:
        if not supabase:
            raise HTTPException(status_code=500, detail="Database not connected")
        
        # Check if product exists
        products = get_table_data("products", {"id": product_id})
        if not products:
            raise HTTPException(status_code=404, detail="Product not found")
        
        product = products[0]
        
        # Check if product is in any active orders (skip this check for now to allow deletion)
        # orders = get_table_data("mobile_orders")
        # for order in orders:
        #     for item in order.get("items", []):
        #         if item.get("product_id") == product_id:
        #             raise HTTPException(
        #                 status_code=400,
        #                 detail="Cannot delete product. It exists in order history."
        #             )
        
        # Delete product image if exists
        if product.get("image_url") and product["image_url"].startswith("/uploads/"):
            try:
                file_path = Path(product["image_url"][1:])  # Remove leading slash
                file_path.unlink(missing_ok=True)
            except Exception as e:
                print(f"Error deleting product image: {e}")
        
        # Delete from cart first
        try:
            delete_table_data("mobile_cart", {"product_id": product_id})
        except Exception as e:
            print(f"Error deleting from cart: {e}")
        
        # Delete product from database
        delete_table_data("products", {"id": product_id})
        return {"message": "Product deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Delete product error: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting product: {str(e)}")

# 📸 SUPABASE STORAGE IMAGE UPLOAD APIs

@app.post("/admin/upload/product-image/{product_id}")
async def upload_product_image(product_id: str, file: UploadFile = File(...)):
    """Upload product image to Supabase Storage (with local fallback)"""
    try:
        if not supabase:
            raise HTTPException(status_code=500, detail="Database not connected")
        
        # Check if product exists
        products = get_table_data("products", {"id": product_id})
        if not products:
            raise HTTPException(status_code=404, detail="Product not found")
        
        # Validate file type
        if not file.content_type or not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="File must be an image")
        
        # Read file content
        file_content = await file.read()
        
        # Validate file size (5MB max)
        if len(file_content) > 5 * 1024 * 1024:  # 5MB
            raise HTTPException(status_code=400, detail="File size must be less than 5MB")
        
        # Generate unique filename
        file_extension = file.filename.split('.')[-1] if file.filename and '.' in file.filename else 'jpg'
        unique_filename = f"product_{product_id}_{uuid.uuid4().hex[:8]}.{file_extension}"
        file_path = f"products/{unique_filename}"
        
        # Try Supabase Storage first
        upload_result = upload_to_supabase_storage(
            file_content=file_content,
            bucket="veggie-images",
            file_path=file_path,
            content_type=file.content_type
        )
        
        if upload_result["success"]:
            # Supabase upload successful
            image_url = upload_result["url"]
            storage_type = "supabase"
        else:
            # Fallback to local storage
            print(f"⚠️ Supabase upload failed: {upload_result['error']}")
            print("📁 Falling back to local storage")
            
            local_file_path = UPLOADS_DIR / "products" / unique_filename
            local_file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(local_file_path, "wb") as buffer:
                buffer.write(file_content)
            
            image_url = f"/uploads/products/{unique_filename}"
            storage_type = "local"
        
        # Update product with image URL
        update_data = {
            "image_url": image_url,
            "updated_at": datetime.now().isoformat()
        }
        
        result = update_table_data("products", update_data, {"id": product_id})
        
        if result:
            return {
                "message": f"Product image uploaded successfully to {storage_type} storage",
                "image_url": image_url,
                "file_size": len(file_content),
                "storage": storage_type
            }
        else:
            # Clean up uploaded file if product update failed
            if storage_type == "supabase":
                delete_from_supabase_storage("veggie-images", file_path)
            else:
                local_file_path.unlink(missing_ok=True)
            raise HTTPException(status_code=500, detail="Failed to update product with image")
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"Upload product image error: {e}")
        raise HTTPException(status_code=500, detail=f"Error uploading image: {str(e)}")

@app.post("/admin/upload/category-image/{category_id}")
async def upload_category_image(category_id: str, file: UploadFile = File(...)):
    """Upload category image to Supabase Storage"""
    try:
        if not supabase:
            raise HTTPException(status_code=500, detail="Database not connected")
        
        # Check if category exists
        categories = get_table_data("categories", {"id": category_id})
        if not categories:
            raise HTTPException(status_code=404, detail="Category not found")
        
        # Validate file type
        if not file.content_type or not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="File must be an image")
        
        # Read file content
        file_content = await file.read()
        
        # Validate file size (5MB max)
        if len(file_content) > 5 * 1024 * 1024:  # 5MB
            raise HTTPException(status_code=400, detail="File size must be less than 5MB")
        
        # Generate unique filename
        file_extension = file.filename.split('.')[-1] if file.filename and '.' in file.filename else 'jpg'
        unique_filename = f"category_{category_id}_{uuid.uuid4().hex[:8]}.{file_extension}"
        file_path = f"categories/{unique_filename}"
        
        # Upload to Supabase Storage
        upload_result = upload_to_supabase_storage(
            file_content=file_content,
            bucket="veggie-images",
            file_path=file_path,
            content_type=file.content_type
        )
        
        if not upload_result["success"]:
            raise HTTPException(status_code=500, detail=f"Upload failed: {upload_result['error']}")
        
        # Update category with Supabase image URL
        image_url = upload_result["url"]
        update_data = {
            "image_url": image_url,
            "updated_at": datetime.now().isoformat()
        }
        
        result = update_table_data("categories", update_data, {"id": category_id})
        
        if result:
            return {
                "message": "Category image uploaded successfully to Supabase",
                "image_url": image_url,
                "file_size": len(file_content),
                "storage": "supabase"
            }
        else:
            # Delete uploaded file if category update failed
            delete_from_supabase_storage("veggie-images", file_path)
            raise HTTPException(status_code=500, detail="Failed to update category with image")
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"Upload category image error: {e}")
        raise HTTPException(status_code=500, detail=f"Error uploading category image: {str(e)}")

@app.delete("/admin/images/product/{product_id}")
def delete_product_image(product_id: str):
    """Delete product image from Supabase Storage"""
    try:
        # Get product to find current image
        products = get_table_data("products", {"id": product_id})
        if not products:
            raise HTTPException(status_code=404, detail="Product not found")
        
        product = products[0]
        current_image_url = product.get("image_url")
        
        if current_image_url:
            # Extract file path from Supabase URL
            # URL format: https://xxx.supabase.co/storage/v1/object/public/veggie-images/products/filename.jpg
            if "veggie-images" in current_image_url:
                # Extract path after bucket name
                path_parts = current_image_url.split("veggie-images/")
                if len(path_parts) > 1:
                    file_path = path_parts[1]
                    
                    # Delete from Supabase Storage
                    delete_result = delete_from_supabase_storage("veggie-images", file_path)
                    if not delete_result["success"]:
                        print(f"Warning: Could not delete image from storage: {delete_result['error']}")
        
        # Update product to remove image URL
        update_data = {
            "image_url": None,
            "updated_at": datetime.now().isoformat()
        }
        
        update_table_data("products", update_data, {"id": product_id})
        
        return {"message": "Product image deleted successfully from Supabase"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Delete product image error: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting image: {str(e)}")

@app.delete("/admin/images/category/{category_id}")
def delete_category_image(category_id: str):
    """Delete category image from Supabase Storage"""
    try:
        # Get category to find current image
        categories = get_table_data("categories", {"id": category_id})
        if not categories:
            raise HTTPException(status_code=404, detail="Category not found")
        
        category = categories[0]
        current_image_url = category.get("image_url")
        
        if current_image_url:
            # Extract file path from Supabase URL
            if "veggie-images" in current_image_url:
                path_parts = current_image_url.split("veggie-images/")
                if len(path_parts) > 1:
                    file_path = path_parts[1]
                    
                    # Delete from Supabase Storage
                    delete_result = delete_from_supabase_storage("veggie-images", file_path)
                    if not delete_result["success"]:
                        print(f"Warning: Could not delete image from storage: {delete_result['error']}")
        
        # Update category to remove image URL
        update_data = {
            "image_url": None,
            "updated_at": datetime.now().isoformat()
        }
        
        update_table_data("categories", update_data, {"id": category_id})
        
        return {"message": "Category image deleted successfully from Supabase"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Delete category image error: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting category image: {str(e)}")

# 🔧 STORAGE MANAGEMENT UTILITY FUNCTIONS

@app.get("/admin/storage/info")
def get_storage_info():
    """Get storage bucket information"""
    try:
        # List buckets
        buckets = supabase.storage.list_buckets()
        
        return {
            "storage_provider": "Supabase Storage",
            "buckets": buckets,
            "image_bucket": "veggie-images",
            "features": [
                "Permanent storage",
                "CDN delivery", 
                "Image optimization",
                "Global distribution"
            ]
        }
    except Exception as e:
        return {"error": f"Could not fetch storage info: {str(e)}"}

@app.post("/admin/storage/create-bucket")
def create_storage_bucket():
    """Create the veggie-images bucket if it doesn't exist"""
    try:
        # Create bucket
        result = supabase.storage.create_bucket(
            "veggie-images",
            options={"public": True}  # Make images publicly accessible
        )
        
        return {
            "message": "Storage bucket created successfully",
            "bucket": "veggie-images",
            "public": True
        }
    except Exception as e:
        return {"error": f"Could not create bucket: {str(e)}")

# 🏷️ BANNER MANAGEMENT APIs

class BannerCreate(BaseModel):
    """Create new banner"""
    title: str
    description: Optional[str] = ""
    link_url: Optional[str] = "/products"
    display_order: int = 1
    is_active: bool = True

@app.get("/admin/banners")
def get_admin_banners():
    """Get all banners for admin management"""
    try:
        banners = get_table_data("banners")
        return {
            "banners": sorted(banners, key=lambda x: x.get("display_order", 0)),
            "total_count": len(banners)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching banners: {str(e)}")

@app.post("/admin/banners")
def create_banner(banner: BannerCreate):
    """Create new banner"""
    try:
        banner_data = {
            **banner.dict(),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        result = insert_table_data("banners", banner_data)
        return {
            "message": "Banner created successfully",
            "banner": result.data[0] if result.data else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating banner: {str(e)}")

@app.put("/admin/banners/{banner_id}")
def update_banner(banner_id: str, banner_data: dict):
    """Update banner"""
    try:
        update_data = {
            **banner_data,
            "updated_at": datetime.now().isoformat()
        }
        
        result = update_table_data("banners", update_data, {"id": banner_id})
        
        if result:
            return {"message": "Banner updated successfully"}
        else:
            raise HTTPException(status_code=404, detail="Banner not found")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating banner: {str(e)}")

@app.delete("/admin/banners/{banner_id}")
def delete_banner(banner_id: str):
    """Delete banner"""
    try:
        supabase.table("banners").delete().eq("id", banner_id).execute()
        return {"message": "Banner deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting banner: {str(e)}")

@app.post("/admin/upload/banner-image/{banner_id}")
def upload_banner_image(banner_id: str, file: UploadFile = File(...)):
    """Upload banner image"""
    try:
        # Validate file type
        if not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="File must be an image")
        
        # Create unique filename
        file_extension = file.filename.split('.')[-1]
        unique_filename = f"banner_{banner_id}_{uuid.uuid4().hex[:8]}.{file_extension}"
        file_path = UPLOADS_DIR / "banners" / unique_filename
        
        # Save file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Update banner with image URL
        image_url = f"/uploads/banners/{unique_filename}"
        update_data = {
            "image_url": image_url,
            "updated_at": datetime.now().isoformat()
        }
        
        result = update_table_data("banners", update_data, {"id": banner_id})
        
        if result:
            return {
                "message": "Banner image uploaded successfully",
                "image_url": image_url
            }
        else:
            # Delete uploaded file if banner update failed
            file_path.unlink(missing_ok=True)
            raise HTTPException(status_code=404, detail="Banner not found")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error uploading banner image: {str(e)}")

# 📊 DELIVERY ANALYTICS

# 🛍️ ADDITIONAL MOBILE APP FEATURES

@app.get("/app/delivery-slots")
def get_delivery_slots():
    """Get available delivery slots"""
    return {
        "slots": [
            {
                "id": "today_morning",
                "label": "Today Morning",
                "time": "8:00 AM - 12:00 PM",
                "available": True
            },
            {
                "id": "today_evening", 
                "label": "Today Evening",
                "time": "4:00 PM - 8:00 PM",
                "available": True
            },
            {
                "id": "tomorrow_morning",
                "label": "Tomorrow Morning", 
                "time": "8:00 AM - 12:00 PM",
                "available": True
            }
        ]
    }

@app.get("/app/user/addresses/{user_phone}")
def get_user_addresses(user_phone: str):
    """Get saved addresses for user"""
    try:
        addresses = get_table_data("user_addresses", {"user_phone": user_phone})
        return {
            "addresses": sorted(addresses, key=lambda x: x.get("created_at", ""), reverse=True)
        }
    except Exception as e:
        return {"addresses": [], "error": str(e)}

@app.post("/app/user/addresses")
def save_user_address(address: DeliveryAddress, user_phone: str = Header(None)):
    """Save address for user"""
    try:
        if not user_phone:
            raise HTTPException(status_code=400, detail="User phone required")
        
        address_data = {
            "user_phone": user_phone,
            **address.dict(),
            "created_at": datetime.now().isoformat()
        }
        
        result = insert_table_data("user_addresses", address_data)
        return {"message": "Address saved", "address_id": result.data[0]["id"] if result.data else None}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving address: {str(e)}")

# 🎯 APP CONFIGURATION

@app.get("/app/config")
def get_app_config():
    """Get app configuration for mobile"""
    return {
        "business_info": {
            "name": "Fresh Veggie Store",
            "phone": "+91-98765-43210",
            "address": "Local Vegetable Market, City",
            "working_hours": "7:00 AM - 9:00 PM"
        },
        "delivery_info": {
            "free_delivery_threshold": 199,
            "delivery_charge": 40,
            "delivery_areas": ["Sector 1", "Sector 2", "Sector 3", "MG Road", "Park Street"],
            "estimated_delivery_time": "30-60 minutes"
        },
        "payment_methods": [
            {"id": "cod", "name": "Cash on Delivery", "available": True},
            {"id": "online", "name": "Online Payment", "available": False}
        ],
        "app_features": {
            "guest_checkout": True,
            "order_tracking": True,
            "address_save": True,
            "search_products": True,
            "category_browse": True
        }
    }

# Startup event to add mobile-friendly sample data
@app.on_event("startup")
async def startup_event():
    """Add sample data for mobile app and setup storage"""
    try:
        print("📱 Mobile Veggie App API starting up...")
        
        # Check Supabase storage setup (non-blocking)
        print("🗄️ Checking Supabase storage setup...")
        try:
            if supabase:
                buckets = supabase.storage.list_buckets()
                bucket_names = [bucket.get("name") for bucket in buckets]
                
                if "veggie-images" not in bucket_names:
                    print("📸 Creating veggie-images bucket...")
                    try:
                        supabase.storage.create_bucket(
                            "veggie-images",
                            options={"public": True}
                        )
                        print("✅ Storage bucket created successfully")
                    except Exception as create_error:
                        print(f"⚠️ Could not create bucket: {create_error}")
                        print("📝 Please create 'veggie-images' bucket manually in Supabase dashboard")
                else:
                    print("✅ Storage bucket already exists")
            else:
                print("⚠️ Supabase not connected - storage features will be limited")
        except Exception as storage_error:
            print(f"⚠️ Storage setup warning: {storage_error}")
            print("📝 Storage features may be limited. App will continue without storage.")
        
        # Check if we need to add sample products
        try:
            products = get_table_data("products")
            if len(products) < 8:
                print("🥬 Adding mobile-friendly vegetable products...")
                await add_mobile_veggie_products()
            
            print(f"✅ Mobile app ready with {len(products)} products")
        except Exception as products_error:
            print(f"⚠️ Could not load products: {products_error}")
            print("📝 App will continue with existing data")
        
        print("🎉 Startup completed successfully!")
        
    except Exception as e:
        print(f"⚠️ Startup warning: {e}")
        print("📝 App will continue to run despite startup issues")

async def add_mobile_veggie_products():
    """Add mobile app optimized vegetables"""
    try:
        categories = get_table_data("categories")
        
        mobile_veggies = [
            # Popular Daily Vegetables
            ("Fresh Onion", "Premium quality red onions", "Onion & Potato", 25.0, 50, True),
            ("Potato", "Fresh potatoes from local farms", "Onion & Potato", 20.0, 60, True),
            ("Tomato", "Fresh ripe tomatoes", "Vegetables", 40.0, 40, True),
            ("Green Chili", "Spicy fresh green chilies", "Vegetables", 60.0, 25, False),
            
            # Leafy Greens
            ("Spinach (Palak)", "Fresh organic spinach", "Leafy Vegetables", 15.0, 30, True),
            ("Coriander", "Fresh coriander leaves", "Leafy Vegetables", 10.0, 25, True),
            ("Mint (Pudina)", "Fresh mint leaves", "Leafy Vegetables", 12.0, 20, False),
            ("Fenugreek (Methi)", "Fresh methi leaves", "Leafy Vegetables", 18.0, 15, False),
            
            # Regular Vegetables
            ("Cauliflower", "Fresh white cauliflower", "Vegetables", 45.0, 20, True),
            ("Cabbage", "Fresh green cabbage", "Vegetables", 25.0, 25, False),
            ("Bell Pepper", "Colorful bell peppers", "Vegetables", 80.0, 15, True),
            ("Cucumber", "Fresh green cucumber", "Vegetables", 30.0, 30, False),
            
            # Exotic/Premium
            ("Baby Corn", "Tender baby corn", "Exotics", 90.0, 12, False),
            ("Broccoli", "Fresh green broccoli", "Exotics", 120.0, 10, True),
        ]
        
        for name, desc, cat_name, price, stock, featured in mobile_veggies:
            category = next((c for c in categories if c["name"] == cat_name), None)
            if category:
                product_data = {
                    "name": name,
                    "description": desc,
                    "category_id": category["id"],
                    "base_price": price,
                    "stock_quantity": stock,
                    "featured": featured,
                    "is_active": True,
                    "weight_options": ["250g", "500g", "1kg"],
                    "unit_options": [1, 2, 3, 4, 5],
                    "discount_percentage": 0,
                    "created_at": datetime.now().isoformat()
                }
                
                insert_table_data("products", product_data)
                print(f"📱 Added: {name} - ₹{price}")
        
    except Exception as e:
        print(f"❌ Error adding mobile vegetables: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)