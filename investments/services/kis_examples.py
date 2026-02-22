from investments.services.kis_overseas_stock import KisOverseasStockClient
from investments.models import Account

acc_1 = Account.objects.get(id=1)
acc_2 = Account.objects.get(id=2)

oversea_client_1 = KisOverseasStockClient(acc_1)
oversea_client_2 = KisOverseasStockClient(acc_2)

df1, df2 = oversea_client_1.inquire_balance()
print(df1)
print(df2)

df3, df4 = oversea_client_2.inquire_balance()
print(df3)
print(df4)
