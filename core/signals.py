# 특정 event에 대해 "일이 터진 후" 알려주는 알림
from django.dispatch import receiver
from allauth.account.signals import user_signed_up
from allauth.socialaccount.signals import pre_social_login

# 구글 프로필 이미지 업데이트
# 로그인 성공 이후의 부가 작업이라 시그널
def _update_image(user, sociallogin):
    if sociallogin.account.provider == 'google':
        picture_url = sociallogin.account.extra_data.get('picture')
        if picture_url and user.profile_image_url != picture_url:
            user.profile_image_url = picture_url
            user.save(update_fields=['profile_image_url'])

# 가입 직후
@receiver(user_signed_up)
def signal_user_signed_up(request, user, sociallogin, **kwargs):
    if sociallogin:
        _update_image(user, sociallogin)

# 로그인 직후
@receiver(pre_social_login)
def signal_pre_social_login(request, sociallogin, **kwargs):
    # 이미 가입된 유저(기존 유저)인 경우에만 로그인 시 업데이트
    if sociallogin.is_existing:
        _update_image(sociallogin.user, sociallogin)