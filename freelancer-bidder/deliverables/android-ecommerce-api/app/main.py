"""
Android E-Commerce REST API
Bid project: Android E-Commerce API Development

Run:
  pip install -r requirements.txt
  uvicorn app.main:app --reload --port 8000

Docs: http://127.0.0.1:8000/docs
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import bcrypt
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import Float, ForeignKey, Integer, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

SECRET_KEY = "change-me-in-production-android-ecommerce"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

engine = create_engine("sqlite:///./ecommerce.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255), default="")


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(2000), default="")
    price: Mapped[float] = mapped_column(Float)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    image_url: Mapped[str] = mapped_column(String(500), default="")


class CartItem(Base):
    __tablename__ = "cart_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    product: Mapped[Product] = relationship()


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    total: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    created_at: Mapped[str] = mapped_column(String(40), default="")
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[float] = mapped_column(Float)
    order: Mapped[Order] = relationship(back_populates="items")


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    full_name: str = ""


class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ProductIn(BaseModel):
    name: str
    description: str = ""
    price: float = Field(gt=0)
    stock: int = Field(ge=0)
    image_url: str = ""


class ProductOut(ProductIn):
    id: int

    class Config:
        from_attributes = True


class CartItemIn(BaseModel):
    product_id: int
    quantity: int = Field(ge=1, default=1)


class CartItemOut(BaseModel):
    id: int
    product_id: int
    quantity: int
    product_name: str
    unit_price: float
    line_total: float


class OrderOut(BaseModel):
    id: int
    total: float
    status: str
    created_at: str
    items: list[dict]


app = FastAPI(
    title="Android E-Commerce API",
    version="1.0.0",
    description="Clean REST API for an Android-only e-commerce client.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbDep = Annotated[Session, Depends(get_db)]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": subject, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], db: DbDep
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str | None = payload.get("sub")
        if not email:
            raise credentials_exception
    except JWTError as exc:
        raise credentials_exception from exc
    user = db.scalar(select(User).where(User.email == email))
    if not user:
        raise credentials_exception
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def seed_products(db: Session) -> None:
    if db.scalar(select(Product).limit(1)):
        return
    samples = [
        Product(name="Wireless Earbuds", description="Bluetooth 5.3", price=29.99, stock=120, image_url=""),
        Product(name="USB-C Charger", description="30W fast charge", price=19.5, stock=200, image_url=""),
        Product(name="Phone Case", description="Shockproof clear case", price=12.0, stock=300, image_url=""),
    ]
    db.add_all(samples)
    db.commit()


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_products(db)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/register", response_model=UserOut)
def register(payload: UserCreate, db: DbDep):
    exists = db.scalar(select(User).where(User.email == payload.email))
    if exists:
        raise HTTPException(400, "Email already registered")
    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.post("/auth/login", response_model=Token)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbDep):
    user = db.scalar(select(User).where(User.email == form.username))
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(400, "Incorrect email or password")
    return Token(access_token=create_access_token(user.email))


@app.get("/me", response_model=UserOut)
def me(user: CurrentUser):
    return user


@app.get("/products", response_model=list[ProductOut])
def list_products(db: DbDep):
    return list(db.scalars(select(Product).order_by(Product.id)).all())


@app.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: DbDep):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    return product


@app.post("/products", response_model=ProductOut)
def create_product(payload: ProductIn, db: DbDep, _: CurrentUser):
    product = Product(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@app.get("/cart", response_model=list[CartItemOut])
def get_cart(user: CurrentUser, db: DbDep):
    items = db.scalars(select(CartItem).where(CartItem.user_id == user.id)).all()
    out = []
    for item in items:
        out.append(
            CartItemOut(
                id=item.id,
                product_id=item.product_id,
                quantity=item.quantity,
                product_name=item.product.name,
                unit_price=item.product.price,
                line_total=round(item.product.price * item.quantity, 2),
            )
        )
    return out


@app.post("/cart/items", response_model=list[CartItemOut])
def add_cart_item(payload: CartItemIn, user: CurrentUser, db: DbDep):
    product = db.get(Product, payload.product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    if product.stock < payload.quantity:
        raise HTTPException(400, "Insufficient stock")
    item = db.scalar(
        select(CartItem).where(
            CartItem.user_id == user.id, CartItem.product_id == payload.product_id
        )
    )
    if item:
        item.quantity += payload.quantity
    else:
        item = CartItem(user_id=user.id, product_id=payload.product_id, quantity=payload.quantity)
        db.add(item)
    db.commit()
    return get_cart(user, db)


@app.delete("/cart/items/{item_id}")
def remove_cart_item(item_id: int, user: CurrentUser, db: DbDep):
    item = db.get(CartItem, item_id)
    if not item or item.user_id != user.id:
        raise HTTPException(404, "Cart item not found")
    db.delete(item)
    db.commit()
    return {"ok": True}


@app.post("/orders", response_model=OrderOut)
def checkout(user: CurrentUser, db: DbDep):
    items = list(db.scalars(select(CartItem).where(CartItem.user_id == user.id)).all())
    if not items:
        raise HTTPException(400, "Cart is empty")

    total = 0.0
    order = Order(
        user_id=user.id,
        status="pending",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    db.add(order)
    db.flush()

    for item in items:
        product = item.product
        if product.stock < item.quantity:
            raise HTTPException(400, f"Insufficient stock for {product.name}")
        product.stock -= item.quantity
        line = product.price * item.quantity
        total += line
        db.add(
            OrderItem(
                order_id=order.id,
                product_id=product.id,
                quantity=item.quantity,
                unit_price=product.price,
            )
        )
        db.delete(item)

    order.total = round(total, 2)
    order.status = "paid_demo"  # payment gateway hook point
    db.commit()
    db.refresh(order)
    return OrderOut(
        id=order.id,
        total=order.total,
        status=order.status,
        created_at=order.created_at,
        items=[
            {
                "product_id": i.product_id,
                "quantity": i.quantity,
                "unit_price": i.unit_price,
            }
            for i in order.items
        ],
    )


@app.get("/orders", response_model=list[OrderOut])
def list_orders(user: CurrentUser, db: DbDep):
    orders = db.scalars(select(Order).where(Order.user_id == user.id).order_by(Order.id.desc())).all()
    return [
        OrderOut(
            id=o.id,
            total=o.total,
            status=o.status,
            created_at=o.created_at,
            items=[
                {
                    "product_id": i.product_id,
                    "quantity": i.quantity,
                    "unit_price": i.unit_price,
                }
                for i in o.items
            ],
        )
        for o in orders
    ]
