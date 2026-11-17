SHOPSPHERE PRODUCT RATINGS & REVIEWS

Added in this update:
- Product average rating and review count on product cards and detail pages.
- Customer reviews with a 1-to-5 star rating and optional written comment.
- Reviews are accepted only for products included in that customer's Delivered orders.
- One review per customer, product, and delivered order (database uniqueness constraint).
- Customers can delete their own reviews.
- Average ratings are calculated from stored reviews; no fake/demo ratings are inserted.

DATABASE NOTE:
The product_reviews table is created automatically by init_db() when the app starts.
Existing shopsphere.db files are upgraded automatically; do not delete your existing database.

To run:
  py -m pip install -r requirements.txt
  py app.py
