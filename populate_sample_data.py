#!/usr/bin/env python3
"""
Script para poblar la base de datos del POS con datos de ejemplo.
Ejecutar después de que las tablas estén creadas.
"""

from sqlalchemy.orm import sessionmaker
from db import engine, Category, Product

def populate_sample_data():
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    try:
        # Crear categorías
        categories_data = [
            {"name": "Bebidas", "description": "Refrescos, jugos y bebidas", "color": "#00A8E8"},
            {"name": "Snacks", "description": "Botanas y aperitivos", "color": "#FFC107"},
            {"name": "Lácteos", "description": "Leche, queso y productos lácteos", "color": "#00C853"},
            {"name": "Panadería", "description": "Pan, pasteles y productos de panadería", "color": "#F44336"},
            {"name": "Limpieza", "description": "Productos de limpieza y hogar", "color": "#9C27B0"},
        ]

        categories = []
        for cat_data in categories_data:
            category = Category(**cat_data)
            db.add(category)
            categories.append(category)

        db.commit()

        # Crear productos
        products_data = [
            # Bebidas
            {"name": "Coca Cola 600ml", "price": 15.50, "cost": 12.00, "category_id": 1, "stock_quantity": 50, "sku": "BEV001"},
            {"name": "Jugo de Naranja 1L", "price": 25.00, "cost": 18.00, "category_id": 1, "stock_quantity": 30, "sku": "BEV002"},
            {"name": "Agua Mineral 500ml", "price": 10.00, "cost": 7.00, "category_id": 1, "stock_quantity": 100, "sku": "BEV003"},

            # Snacks
            {"name": "Papas Sabritas 45g", "price": 12.50, "cost": 9.00, "category_id": 2, "stock_quantity": 80, "sku": "SNK001"},
            {"name": "Galletas Oreo 154g", "price": 18.00, "cost": 13.00, "category_id": 2, "stock_quantity": 40, "sku": "SNK002"},
            {"name": "Chocolate Hershey's 43g", "price": 8.50, "cost": 6.00, "category_id": 2, "stock_quantity": 60, "sku": "SNK003"},

            # Lácteos
            {"name": "Leche Lala 1L", "price": 22.00, "cost": 16.00, "category_id": 3, "stock_quantity": 25, "sku": "DAI001"},
            {"name": "Queso Panela 500g", "price": 45.00, "cost": 35.00, "category_id": 3, "stock_quantity": 15, "sku": "DAI002"},
            {"name": "Yogurt Danone 1kg", "price": 28.00, "cost": 20.00, "category_id": 3, "stock_quantity": 20, "sku": "DAI003"},

            # Panadería
            {"name": "Pan Blanco Bimbo", "price": 35.00, "cost": 25.00, "category_id": 4, "stock_quantity": 12, "sku": "BAK001"},
            {"name": "Pastel de Chocolate", "price": 85.00, "cost": 60.00, "category_id": 4, "stock_quantity": 5, "sku": "BAK002"},
            {"name": "Conchas Variadas 6pzs", "price": 42.00, "cost": 30.00, "category_id": 4, "stock_quantity": 8, "sku": "BAK003"},

            # Limpieza
            {"name": "Jabón Zote 200g", "price": 16.50, "cost": 12.00, "category_id": 5, "stock_quantity": 35, "sku": "CLE001"},
            {"name": "Detergente Ariel 500g", "price": 55.00, "cost": 40.00, "category_id": 5, "stock_quantity": 18, "sku": "CLE002"},
            {"name": "Cloro Clorox 1L", "price": 15.00, "cost": 10.00, "category_id": 5, "stock_quantity": 22, "sku": "CLE003"},
        ]

        for prod_data in products_data:
            product = Product(**prod_data)
            db.add(product)

        db.commit()

        print("✅ Datos de ejemplo insertados correctamente!")
        print(f"   - {len(categories)} categorías creadas")
        print(f"   - {len(products_data)} productos creados")

    except Exception as e:
        print(f"❌ Error insertando datos: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    populate_sample_data()