from rest_framework import generics, permissions
from .models import Product, Order, Payment
from .serializers import ProductSerializer, OrderSerializer, RegisterSerializer

from django.contrib.auth.models import User
from rest_framework.response import Response
from rest_framework import status
import stripe
from django.conf import settings
from rest_framework.views import APIView
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
#from rest_framework.permissions import IsAuthenticated, IsAdminUser

# Create your views here.


class ProductListView(generics.ListCreateAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.AllowAny()]
        return [permissions.AllowAny()]

class ProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [permissions.AllowAny]

class OrderListCreateView(generics.ListCreateAPIView):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response({"message": "User registered successfully!"}, status=status.HTTP_201_CREATED)
    
#Integrating stripe

#stripe.api_key = settings.STRIPE_SECRET_KEY

class CreateCheckoutSessionView(APIView):
    def post(self, request):
        try:
            amount = float(request.data.get("amount"))
            if not amount:
                return Response({"error": "Amount is required"}, status=status.HTTP_400_BAD_REQUEST)

            # Convert to cents
            amount_in_cents = int(amount * 100)

            # Create Stripe Checkout Session
            session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': 'usd',
                        'product_data': {'name': 'E-commerce Order'},
                        'unit_amount': amount_in_cents,
                    },
                    'quantity': 1,
                }],
                mode='payment',
                success_url='https://your-frontend.com/success?session_id={CHECKOUT_SESSION_ID}',
                cancel_url='https://your-frontend.com/cancel',
            )

            # Create Payment record
            Payment.objects.create(
                user=request.user,
                amount=amount,
                currency='usd',
                stripe_payment_intent=session.payment_intent
            )

            return Response({"sessionId": session.id, "url": session.url})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
@method_decorator(csrf_exempt, name='dispatch')
class StripeWebhookView(APIView):
    def post(self, request):
        payload = request.body
        sig_header = request.META['HTTP_STRIPE_SIGNATURE']
        endpoint_secret = 'your_webhook_secret'  # From your Stripe dashboard

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, endpoint_secret
            )
        except stripe.error.SignatureVerificationError:
            return Response(status=400)

        # Handle payment success
        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']
            intent_id = session.get('payment_intent')

            payment = Payment.objects.filter(stripe_payment_intent=intent_id).first()
            if payment:
                payment.paid = True
                payment.save()

        return Response(status=200)