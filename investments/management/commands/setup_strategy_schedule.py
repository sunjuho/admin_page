# 매매 전략 배치 스케줄 등록/수정
# 사용법: python manage.py setup_strategy_schedule --time 22:40
from datetime import datetime, time, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django_q.models import Schedule

SCHEDULE_NAME = "매매 전략 배치"


class Command(BaseCommand):
    help = "매매 전략이 선택된 계좌들을 매일 지정 시각에 실행하는 django-q 스케줄을 등록합니다."

    def add_arguments(self, parser):
        parser.add_argument("--time", default="22:40",
                            help="매일 실행 시각 (HH:MM, 한국시간). 기본값 22:40 (미국장 개장 직후)")

    def handle(self, *args, **options):
        try:
            run_at = datetime.strptime(options["time"], "%H:%M").time()
        except ValueError:
            raise CommandError("--time 은 HH:MM 형식이어야 합니다. (예: 22:40)")

        schedule, created = Schedule.objects.update_or_create(
            name=SCHEDULE_NAME,
            defaults={
                "func": "investments.services.tasks.run_all_strategies",
                "schedule_type": Schedule.DAILY,
                "next_run": self._next_run(run_at),
                "repeats": -1,  # 무한 반복
            },
        )

        action = "등록" if created else "수정"
        self.stdout.write(self.style.SUCCESS(
            f"'{SCHEDULE_NAME}' 스케줄 {action} 완료 (다음 실행: {timezone.localtime(schedule.next_run):%Y-%m-%d %H:%M})"
        ))

    @staticmethod
    def _next_run(run_at: time):
        # 오늘 해당 시각이 이미 지났으면 내일부터
        now = timezone.localtime()
        next_run = now.replace(hour=run_at.hour, minute=run_at.minute, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        return next_run
