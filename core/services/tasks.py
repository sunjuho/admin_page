from django.contrib.auth.models import User
from datetime import timedelta
from django.utils import timezone


def check_dormant_users():
    # 30일 동안 로그인 안 한 사용자 조회 (예시)
    last_month = timezone.now() - timedelta(days=30)
    target_users = User.objects.filter(last_login__lt=last_month)

    count = target_users.count()

    # 실제 비즈니스 로직 (메일 발송 등)
    # print() 내용은 qcluster 터미널 창에 출력됩니다.
    print(f"--- 배치 작업 시작: {timezone.now()} ---")
    print(f"대상 사용자 수: {count}명")

    for user in target_users:
        # 여기에 알림 발송 로직 추가
        print(f"알림 발송 대상: {user.username}")

    print("--- 배치 작업 완료 ---")


    # info 콘솔에 찍힌 결과.
    '''
    23:03:26 [Q] INFO Enqueued [my_project_cluster] 1
    23:03:26 [Q] INFO Process-947d28948bdc45238a04bcad4c89ff03 created task west-july-stream-virginia from schedule [휴면 유저 체크 배치]
    23:03:26 [Q] INFO Process-f6037525646b4d80bc9c47b6b77de71e processing west-july-stream-virginia 'core.tasks.check_dormant_users' [휴면 유저 체크 배치]
    --- 배치 작업 시작: 2026-02-11 14:03:26.234006+00:00 ---
    대상 사용자 수: 0명
    --- 배치 작업 완료 ---
    23:03:26 [Q] INFO Processed 'core.tasks.check_dormant_users' (west-july-stream-virginia)
    '''
    return f"{count}명 처리 완료"  # 이 리턴값은 DB에 결과로 저장됩니다.

