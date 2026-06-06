# Razorpay Integration Setup Guide

## Overview
This guide will help you set up Razorpay test payment integration for the Lume Restaurant application.

## Step 1: Get Razorpay Test Credentials

1. Go to [Razorpay Dashboard](https://dashboard.razorpay.com/)
2. Sign up or log in to your account
3. Switch to **Test Mode** (toggle in the left sidebar)
4. Go to **Settings** → **API Keys**
5. Generate Test API Keys if you haven't already
6. Copy your:
   - **Key ID** (starts with `rzp_test_`)
   - **Key Secret**

## Step 2: Configure Credentials

### Option A: Using Environment Variables (Recommended)
Set environment variables before running the app:

```bash
export RAZORPAY_KEY_ID='rzp_test_your_key_id_here'
export RAZORPAY_KEY_SECRET='your_key_secret_here'
```

### Option B: Direct Configuration
Edit `app.py` and replace the test credentials:

```python
RAZORPAY_KEY_ID = 'rzp_test_your_actual_key_id'
RAZORPAY_KEY_SECRET = 'your_actual_key_secret'
```

## Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

This will install the `razorpay` Python SDK along with other dependencies.

## Step 4: Run the Application

```bash
python app.py
```

The app will run on `http://localhost:5001` by default.

## Step 5: Test the Payment Flow

1. Navigate to the menu page: `http://localhost:5001/table/5`
2. Add items to your cart
3. Click "Place Order"
4. Razorpay checkout modal will open
5. Use these test card details:

### Test Card Details

**Successful Payment:**
- Card Number: `4111 1111 1111 1111`
- CVV: Any 3 digits (e.g., `123`)
- Expiry: Any future date (e.g., `12/25`)
- Name: Any name

**Failed Payment:**
- Card Number: `4000 0000 0000 0002`
- CVV: Any 3 digits
- Expiry: Any future date

### Test UPI
- UPI ID: `success@razorpay`

### Test Netbanking
- Select any bank
- Use credentials provided on the test page

## Payment Flow

1. **User adds items to cart** → Cart displayed with total
2. **User clicks "Place Order"** → Backend creates Razorpay order
3. **Razorpay Checkout opens** → User enters payment details
4. **Payment processed** → Razorpay returns payment details
5. **Backend verifies payment** → Signature verification
6. **Order confirmed** → Redirects to order status page

## Features Implemented

- ✅ Razorpay order creation
- ✅ Payment checkout integration
- ✅ Payment signature verification
- ✅ Order tracking with payment details
- ✅ Test mode support
- ✅ Error handling and user feedback

## Important Notes

- **Always use test mode** for development
- Never commit your API keys to version control
- Use environment variables in production
- Test mode payments are free and don't charge real money
- Razorpay dashboard shows all test transactions

## Troubleshooting

### "Payment verification failed"
- Check if your API credentials are correct
- Ensure you're using test mode keys with test cards
- Check network connectivity

### "Could not create order"
- Verify Razorpay SDK is installed: `pip install razorpay`
- Check API key configuration in `app.py`
- Review server logs for detailed error messages

### Payment modal doesn't open
- Check browser console for JavaScript errors
- Ensure Razorpay checkout script is loaded
- Verify internet connection

## Production Checklist

Before going live:
- [ ] Switch to Live Mode in Razorpay Dashboard
- [ ] Generate Live API Keys
- [ ] Update environment variables with live keys
- [ ] Enable required payment methods
- [ ] Complete KYC verification
- [ ] Test with real payment methods
- [ ] Set up webhooks for payment status updates
- [ ] Implement proper logging and monitoring

## Support

- [Razorpay Documentation](https://razorpay.com/docs/)
- [Razorpay API Reference](https://razorpay.com/docs/api/)
- [Test Cards & Payment Methods](https://razorpay.com/docs/payments/payments/test-card-details/)
