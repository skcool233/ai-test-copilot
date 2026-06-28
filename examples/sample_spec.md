# 优惠券核销接口

`POST /api/coupons/redeem`

请求体：
- `coupon_code` (string, 必填)：优惠券码，6~16 位字母数字
- `user_id` (string, 必填)：用户 ID
- `order_amount` (number, 必填)：订单金额，单位元，> 0

规则：
- 优惠券须存在、未过期、未被使用
- 订单金额需达到优惠券的最低使用门槛
- 同一用户同一券只能用一次
- 成功返回抵扣金额与最终应付金额；失败返回对应错误码
