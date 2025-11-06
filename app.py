import mysql.connector
from flask import Flask, render_template, request, session, redirect, url_for, flash
from functools import wraps
import random

# --- FLASK APP SETUP ---
app = Flask(__name__)
# IMPORTANT: Use a complex key for production
app.secret_key = 'your_secret_key_here_shweta_123'

# --- DATABASE CONFIGURATION (FIXED) ---
DB_USER = "root"
DB_PASSWORD = ""
DB_HOST = "127.0.0.1"
DB_NAME = "project"
# ----------------------------------------------------------------

# Helper function to connect to the database
def get_db_connection():
    try:
        conn = mysql.connector.connect(
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            database=DB_NAME
        )
        return conn
    except mysql.connector.Error as err:
        print(f"Database connection error: {err}")
        return None

# Decorator to ensure a user is logged in
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in_user' not in session or 'user_id' not in session:
            return redirect(url_for('index', error='You must log in to view this page.'))
        return f(*args, **kwargs)
    return decorated_function

# --- Image Mapping Function ---
def get_image_map():
    """Returns a dictionary mapping product names to their static file paths."""
    return {
        'Galaxy S24 Ultra': '/static/images/s24_ultra.jpg',
        'Galaxy Z Fold 5': '/static/images/zfold5.jpg',
        'Galaxy A54': '/static/images/a54.jpg',
        'Galaxy Buds Pro 2': '/static/images/buds_pro2.jpg',
        '45W USB-C Travel Adapter': '/static/images/charger_45w.jpg',
        'S24 Ultra Silicone Case': '/static/images/silicone_case.jpg',
    }

# Function to fetch product data
def get_product_data():
    conn = get_db_connection()
    if conn is None:
        return {}

    cursor = conn.cursor(dictionary=True)
    image_map = get_image_map()

    query = """
    SELECT 
        pm.model_id AS id, 
        pm.model_name AS name, 
        pc.category_name, 
        ps.series_name, 
        pm.price,
        i.quantity_in_stock AS inventory_count
    FROM PRODUCT_MODEL pm
    JOIN PRODUCT_SERIES ps ON pm.series_id = ps.series_id
    JOIN PRODUCT_CATEGORY pc ON ps.category_id = pc.category_id
    JOIN INVENTORY i ON pm.model_id = i.model_id
    WHERE i.quantity_in_stock > 0 
    ORDER BY pc.category_name, ps.series_name, pm.model_name;
    """
    
    menu_data = {}
    try:
        cursor.execute(query)
        products = cursor.fetchall()

        for product in products:
            # FIX 1: Convert Decimal price to Python float (Resolves TypeError on price access)
            if product.get('price') is not None:
                product['price'] = float(product['price'])
            
            product_name = product['name']
            product['image_url'] = image_map.get(product_name, '/static/images/placeholder.jpg')
            
            # Grouping logic
            category = product['category_name']
            series = product['series_name']

            if category not in menu_data:
                menu_data[category] = {}
            if series not in menu_data[category]:
                menu_data[category][series] = []
            
            menu_data[category][series].append(product)

    except Exception as e:
        print(f"Error fetching product data: {e}")
        return {} 
    finally:
        if conn:
            cursor.close()
            conn.close()
            
    return menu_data

# Function to get the current cart count from the DB
def get_db_cart_count(user_id):
    conn = get_db_connection()
    if conn is None:
        return 0
    cursor = conn.cursor()
    try:
        query = "SELECT SUM(quantity) FROM SHOPPING_CART WHERE user_id = %s"
        cursor.execute(query, (user_id,))
        result = cursor.fetchone()
        # Returns the count, defaults to 0 if NULL
        return int(result[0]) if result and result[0] is not None else 0 
    except Exception as e:
        print(f"Error fetching DB cart count: {e}") 
        return 0
    finally:
        cursor.close()
        conn.close()

# --- ROUTE HANDLERS ---

@app.route('/')
def index():
    error = request.args.get('error')
    signup_success = request.args.get('signup_success')
    return render_template('index.html', error=error, signup_success=signup_success)


@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']
    
    conn = get_db_connection()
    if conn is None:
        return render_template('index.html', error='Database connection failed. Please try again.')

    cursor = conn.cursor()
    
    # CRITICAL: Selects user_id as the first column
    query = "SELECT user_id, username FROM users WHERE username = %s AND password = %s"
    cursor.execute(query, (username, password))
    user_data = cursor.fetchone() 
    
    cursor.close()
    conn.close()

    if user_data:
        # CRITICAL: Store the retrieved user_id (user_data[0])
        session['user_id'] = user_data[0] 
        session['logged_in_user'] = user_data[1]
        return redirect(url_for('product_page'))
    else:
        return render_template('index.html', error='Invalid credentials.')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index', signup_success='You have been successfully logged out.'))


@app.route('/signup_page')
def signup_page():
    return render_template('signup.html')


@app.route('/signup_action', methods=['POST'])
def signup_action():
    username = request.form['username']
    email = request.form['email']
    password = request.form['password']

    conn = get_db_connection()
    if conn is None:
        return render_template('index.html', error='Database connection failed. Cannot sign up at this time.')
    
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT username FROM users WHERE username = %s", (username,))
        if cursor.fetchone():
            return render_template('index.html', error='Username already taken. Please choose another.')

        insert_query = "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)" 
        cursor.execute(insert_query, (username, email, password))
        
        conn.commit()

        return render_template('index.html', signup_success='Account created successfully! Please log in.')

    except Exception as e:
        print(f"Error during sign up or database operation: {e}")
        conn.rollback() 
        return render_template('index.html', error=f'An unexpected error occurred during sign up. Check terminal for details.')
        
    finally:
        if conn:
            cursor.close()
            conn.close()


@app.route('/products')
@login_required
def product_page():
    menu_data = get_product_data()
    user_id = session.get('user_id')
    
    return render_template(
        'products.html',
        logged_in_user=session.get('logged_in_user'),
        menu_data=menu_data,
        cart_count=get_db_cart_count(user_id) # Gets count from DB
    )


# Add to cart: Inserts/updates SHOPPING_CART table
@app.route('/add_to_cart/<int:model_id>/<string:model_name>/<float:price>', methods=['POST'])
@login_required
def add_to_cart(model_id, model_name, price):
    user_id = session.get('user_id')
    
    conn = get_db_connection()
    if conn is None:
        flash("Failed to connect to the database.")
        return redirect(url_for('product_page'))

    cursor = conn.cursor()
    
    try:
        # Check if item is already in the cart for this user
        check_query = "SELECT quantity FROM SHOPPING_CART WHERE user_id = %s AND model_id = %s"
        cursor.execute(check_query, (user_id, model_id))
        cart_item = cursor.fetchone()

        if cart_item:
            # Update quantity
            update_query = "UPDATE SHOPPING_CART SET quantity = quantity + 1 WHERE user_id = %s AND model_id = %s"
            cursor.execute(update_query, (user_id, model_id))
        else:
            # FIX 3: Use 3 placeholders (%s, %s, %s) and pass 3 values (user_id, model_id, 1)
            insert_query = "INSERT INTO SHOPPING_CART (user_id, model_id, quantity) VALUES (%s, %s, %s)"
            cursor.execute(insert_query, (user_id, model_id, 1))
            
        conn.commit()
        flash(f"{model_name} successfully added to cart!")
        
    except Exception as e:
        conn.rollback()
        print(f"DATABASE ERROR during Add to Cart: {e}") 
        flash(f"Failed to add item to cart. Error: {e}")
        
    finally:
        cursor.close()
        conn.close()
        
    return render_template('add_confirm.html', model_name=model_name)


# View cart: Fetches from SHOPPING_CART table
@app.route('/view_cart')
@login_required
def view_cart():
    user_id = session.get('user_id')
    conn = get_db_connection()
    if conn is None:
        flash("Cannot view cart: Database connection failed.")
        return redirect(url_for('product_page'))
        
    cursor = conn.cursor(dictionary=True)
    cart_items = []
    subtotal = 0

    try:
        query = """
        SELECT sc.model_id, pm.model_name, pm.price, sc.quantity 
        FROM SHOPPING_CART sc 
        JOIN PRODUCT_MODEL pm ON sc.model_id = pm.model_id 
        WHERE sc.user_id = %s
        """
        cursor.execute(query, (user_id,))
        cart_items = cursor.fetchall()
        
        # FIX 2: Explicitly convert Decimal price to float during calculation (Prevents TypeError)
        subtotal = sum(
            float(item.get('price') or 0.0) * (item.get('quantity') or 0) 
            for item in cart_items
        )
        
    except Exception as e:
        print(f"Error fetching cart items: {e}")
    finally:
        cursor.close()
        conn.close()

    tax_rate = 0.10
    tax = subtotal * tax_rate
    total = subtotal + tax
    
    return render_template(
        'cart.html',
        cart_items=cart_items,
        cart_count=get_db_cart_count(user_id),
        subtotal=subtotal,
        tax=tax,
        total=total
    )


# Place Order: Uses DB Cart, Generates Random ID, Clears Cart
@app.route('/place_order_action', methods=['POST'])
@login_required
def place_order_action():
    user_id = session.get('user_id')
    conn = get_db_connection()
    if conn is None:
        return render_template('order_result.html', success=False, message='Database connection failed during checkout.')

    cursor = conn.cursor(dictionary=True)
    
    # 1. Fetch items from the SHOPPING_CART
    cart_items = []
    try:
        cursor.execute("""
            SELECT sc.model_id, pm.model_name, pm.price, sc.quantity 
            FROM SHOPPING_CART sc 
            JOIN PRODUCT_MODEL pm ON sc.model_id = pm.model_id 
            WHERE sc.user_id = %s
        """, (user_id,))
        cart_items = cursor.fetchall()
    except Exception as e:
        print(f"Error fetching cart items for order: {e}")
        return render_template('order_result.html', success=False, message='Failed to retrieve cart items.')

    if not cart_items:
        return redirect(url_for('view_cart'))

    # 2. Transaction Logic
    # FIX 4: Removed conn.start_transaction() to avoid "Transaction already in progress" error.
    # The first INSERT query implicitly starts the transaction.
    
    order_id = str(random.randint(100000, 999999)) 
    
    # Calculate total price, ensuring Decimal is cast to float
    total_price = sum(float(item.get('price') or 0.0) * (item.get('quantity') or 0) for item in cart_items) * 1.10 # + 10% tax

    try:
        # (FIXED) Insert into ORDERS table (Starts implicit transaction)
        order_query = "INSERT INTO ORDERS (order_id, user_id, total_amount, order_date) VALUES (%s, %s, %s, NOW())"
        cursor.execute(order_query, (order_id, user_id, total_price)) 

        for item in cart_items:
            # Insert into ORDER_ITEMS
            detail_query = "INSERT INTO ORDER_ITEMS (order_id, model_id, quantity, unit_price) VALUES (%s, %s, %s, %s)"
            cursor.execute(detail_query, (order_id, item['model_id'], item['quantity'], float(item['price']))) 

            # Update INVENTORY
            update_inventory_query = "UPDATE INVENTORY SET quantity_in_stock = quantity_in_stock - %s WHERE model_id = %s"
            cursor.execute(update_inventory_query, (item['quantity'], item['model_id']))

        # Clear SHOPPING_CART for the user
        clear_cart_query = "DELETE FROM SHOPPING_CART WHERE user_id = %s"
        cursor.execute(clear_cart_query, (user_id,))
            
        conn.commit() # Commits all changes
        
        return render_template('order_result.html', success=True, order_id=order_id, message='Your order has been placed successfully')

    except Exception as e:
        print(f"Transaction failed, rolling back: {e}")
        conn.rollback() # Rolls back all changes if an error occurs
        return render_template('order_result.html', success=False, message=f'Order processing failed due to: {e}. All changes rolled back.')
        
    finally:
        if conn:
            cursor.close()
            conn.close()

if __name__ == '__main__':
    app.run(debug=True)