"""
MeetingScheduler - Handles scheduling and executing meetings using APScheduler
"""
import json
import os
from pathlib import Path
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
from .meet_joiner import MeetJoiner


class MeetingScheduler:
    """Manages scheduled meetings using cron expressions"""
    
    def __init__(self, config_path):
        """
        Initialize scheduler with configuration file
        
        Args:
            config_path (str or Path): Path to meetings.json configuration file
        """
        self.config_path = Path(config_path)
        self.scheduler = BackgroundScheduler()
        self.config = None
        self.scheduled_jobs = []
        
        # Load environment variables
        load_dotenv()
    
    def load_config(self):
        """
        Load meetings configuration from JSON file
        
        Returns:
            bool: True if loaded successfully, False otherwise
        """
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            
            if 'meetings' not in self.config or not isinstance(self.config['meetings'], list):
                print('❌ Invalid meetings configuration: meetings array not found')
                return False
            
            # Validate all meetings
            valid_meetings = []
            invalid_count = 0
            
            for index, meeting in enumerate(self.config['meetings'], 1):
                validation_errors = self._validate_meeting(meeting, index)
                
                if validation_errors:
                    invalid_count += 1
                    print(f'\n❌ Meeting {index} validation failed:')
                    for error in validation_errors:
                        print(f'   - {error}')
                else:
                    valid_meetings.append(meeting)
            
            if invalid_count > 0:
                print(f'\n⚠️  Found {invalid_count} invalid meeting(s)')
                print(f'✅ {len(valid_meetings)} valid meeting(s) will be loaded')
                
                if len(valid_meetings) == 0:
                    print('\n❌ No valid meetings found. Please fix the configuration.')
                    return False
            
            # Replace config with only valid meetings
            self.config['meetings'] = valid_meetings
            
            print(f'\n📋 Successfully loaded {len(valid_meetings)} valid meeting(s)')
            return True
        
        except Exception as error:
            print(f'❌ Error loading meetings config: {str(error)}')
            return False
    
    def _validate_meeting(self, meeting, index):
        """
        Validate a meeting configuration
        
        Args:
            meeting (dict): Meeting configuration
            index (int): Meeting index for error messages
            
        Returns:
            list: List of validation error messages (empty if valid)
        """
        errors = []
        
        # 1. Check if meeting is a dictionary
        if not isinstance(meeting, dict):
            errors.append('Meeting must be a dictionary/object')
            return errors
        
        # 2. Validate 'name' field (required, non-empty)
        name = meeting.get('name', '').strip()
        if not name:
            errors.append('Field "name" is required and cannot be empty')
        elif len(name) < 2:
            errors.append('Field "name" must be at least 2 characters long')
        
        # 3. Validate 'url' field (required, non-empty, valid format)
        url = meeting.get('url', '').strip()
        if not url:
            errors.append('Field "url" is required and cannot be empty')
        else:
            url_errors = self._validate_meeting_url(url)
            errors.extend(url_errors)
        
        # 4. Validate 'schedule' field (required, non-empty, valid format)
        schedule = meeting.get('schedule', '').strip()
        if not schedule:
            errors.append('Field "schedule" is required and cannot be empty')
        else:
            schedule_errors = self._validate_schedule(schedule)
            errors.extend(schedule_errors)
        
        # 5. Validate 'enabled' field (optional, but must be boolean if present)
        if 'enabled' in meeting and not isinstance(meeting['enabled'], bool):
            errors.append('Field "enabled" must be true or false')
        
        return errors
    
    def _validate_meeting_url(self, url):
        """
        Validate Google Meet URL format
        
        Args:
            url (str): Meeting URL to validate
            
        Returns:
            list: List of validation error messages (empty if valid)
        """
        import re
        
        errors = []
        
        # Check if URL starts with correct protocol
        if not url.startswith('https://meet.google.com/'):
            errors.append('URL must start with "https://meet.google.com/"')
            return errors
        
        # Extract meeting code from URL
        # Valid formats:
        # https://meet.google.com/abc-defg-hij (standard format)
        # https://meet.google.com/lookup/xxxxx (lookup format)
        
        # Pattern for standard meeting code: xxx-xxxx-xxx (3-4-3 format)
        standard_pattern = r'^https://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}$'
        
        # Pattern for lookup format
        lookup_pattern = r'^https://meet\.google\.com/lookup/[a-zA-Z0-9_-]+$'
        
        # Check if URL matches either pattern
        if not (re.match(standard_pattern, url, re.IGNORECASE) or 
                re.match(lookup_pattern, url, re.IGNORECASE)):
            errors.append(
                'Invalid Google Meet URL format. '
                'Expected format: https://meet.google.com/xxx-xxxx-xxx '
                '(where x is a letter)'
            )
        
        return errors
    
    def _validate_schedule(self, schedule):
        """
        Validate schedule format (HH:MM or cron expression)
        
        Args:
            schedule (str): Schedule string to validate
            
        Returns:
            list: List of validation error messages (empty if valid)
        """
        errors = []
        
        # Try to parse as HH:MM format
        hour_minute = self._parse_time_string(schedule)
        if hour_minute is not None:
            # Valid HH:MM format
            return errors
        
        # Try to parse as cron expression
        try:
            parts = schedule.split()
            if len(parts) != 5:
                errors.append(
                    'Invalid schedule format. Use "HH:MM" (e.g., "09:00") '
                    'or cron expression (e.g., "0 9 * * 1-5")'
                )
                return errors
            
            # Validate each cron field
            minute, hour, day_of_month, month, day_of_week = parts
            
            # Basic validation (not exhaustive, but catches common errors)
            if not self._is_valid_cron_field(minute, 0, 59):
                errors.append(f'Invalid minute value in cron: "{minute}"')
            
            if not self._is_valid_cron_field(hour, 0, 23):
                errors.append(f'Invalid hour value in cron: "{hour}"')
            
            if not self._is_valid_cron_field(day_of_month, 1, 31):
                errors.append(f'Invalid day of month in cron: "{day_of_month}"')
            
            if not self._is_valid_cron_field(month, 1, 12):
                errors.append(f'Invalid month value in cron: "{month}"')
            
            if not self._is_valid_cron_field(day_of_week, 0, 6):
                errors.append(f'Invalid day of week in cron: "{day_of_week}"')
            
        except Exception as e:
            errors.append(f'Invalid schedule format: {str(e)}')
        
        return errors
    
    def _is_valid_cron_field(self, field, min_val, max_val):
        """
        Validate a single cron field
        
        Args:
            field (str): Cron field value
            min_val (int): Minimum allowed value
            max_val (int): Maximum allowed value
            
        Returns:
            bool: True if valid
        """
        # Wildcard is always valid
        if field == '*':
            return True
        
        # Check for ranges (e.g., "1-5")
        if '-' in field:
            try:
                start, end = field.split('-')
                start_num = int(start)
                end_num = int(end)
                return (min_val <= start_num <= max_val and 
                        min_val <= end_num <= max_val and 
                        start_num <= end_num)
            except:
                return False
        
        # Check for lists (e.g., "1,3,5")
        if ',' in field:
            try:
                values = [int(v) for v in field.split(',')]
                return all(min_val <= v <= max_val for v in values)
            except:
                return False
        
        # Check for step values (e.g., "*/5")
        if '/' in field:
            try:
                base, step = field.split('/')
                if base != '*':
                    base_num = int(base)
                    if not (min_val <= base_num <= max_val):
                        return False
                step_num = int(step)
                return step_num > 0
            except:
                return False
        
        # Check for single number
        try:
            num = int(field)
            return min_val <= num <= max_val
        except:
            return False
    
    def schedule_all_meetings(self):
        """Schedule all enabled meetings from configuration"""
        if not self.config or 'meetings' not in self.config:
            print('❌ No meetings configuration loaded')
            return
        
        # Clear existing jobs
        self.scheduler.remove_all_jobs()
        self.scheduled_jobs = []
        
        enabled_meetings = [m for m in self.config['meetings'] if m.get('enabled', True)]
        
        print(f'\n📅 Scheduling {len(enabled_meetings)} enabled meetings:\n')
        
        for index, meeting in enumerate(enabled_meetings):
            try:
                schedule_value = meeting.get('schedule', '')
                trigger, description = self._build_trigger(schedule_value)
                
                # Schedule the job
                job = self.scheduler.add_job(
                    func=self._join_scheduled_meeting,
                    trigger=trigger,
                    args=[meeting],
                    id=f"meeting_{index}",
                    name=meeting['name']
                )
                
                self.scheduled_jobs.append(job)
                
                print(f'{index + 1}. 📌 {meeting["name"]}')
                print(f'   🔗 {meeting["url"]}')
                print(f'   ⏰ Schedule: {description}\n')
            
            except Exception as error:
                print(f'❌ Error scheduling "{meeting["name"]}": {str(error)}')
        
        print('✅ All meetings scheduled successfully!\n')
    
    def start(self):
        """Start the scheduler"""
        if not self.scheduler.running:
            self.scheduler.start()
            print('🎯 Scheduler started')
    
    def stop(self):
        """Stop the scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            print('🛑 Scheduler stopped')
    
    def _join_scheduled_meeting(self, meeting):
        """
        Join a scheduled meeting
        
        Args:
            meeting (dict): Meeting configuration dictionary
        """
        print('\n' + '=' * 60)
        print(f'🔔 Scheduled meeting triggered: "{meeting["name"]}"')
        print('=' * 60 + '\n')
        
        # Get configuration from environment
        default_solo = int(os.getenv('SOLO_TIMEOUT_MINUTES', '8'))
        default_max_duration = int(os.getenv('MAX_MEETING_MINUTES', '240'))

        config = {
            'headless': os.getenv('HEADLESS', 'false').lower() == 'true',
            'solo_timeout_minutes': int(meeting.get('solo_timeout_minutes', default_solo)),
            'max_meeting_minutes': int(meeting.get('max_meeting_minutes', default_max_duration)),
            'max_retries': int(os.getenv('MAX_RETRY_ATTEMPTS', '3')),
            'retry_delay': int(os.getenv('RETRY_DELAY_SECONDS', '30')),
            'greeting_message': os.getenv('GREETING_MESSAGE', 'Hello everyone'),
        }

        
        joiner = MeetJoiner(config)
        
        try:
            joiner.initialize()
            joiner.join_meeting(meeting['url'], meeting['name'])
        except Exception as error:
            print(f'❌ Error joining meeting "{meeting["name"]}": {str(error)}')
        finally:
            joiner.close()
    
    def _build_trigger(self, schedule_value):
        """Create CronTrigger from HH:MM or cron expression."""
        hour_minute = self._parse_time_string(schedule_value)
        if hour_minute is not None:
            hour, minute = hour_minute
            trigger = CronTrigger(hour=hour, minute=minute)
            description = f'Daily at {str(hour).zfill(2)}:{str(minute).zfill(2)}'
            return trigger, description

        trigger = CronTrigger.from_crontab(schedule_value)
        description = self._describe_cron(schedule_value)
        return trigger, description

    def _parse_time_string(self, schedule_value):
        """Parse HH:MM string into hour/minute tuple."""
        if not schedule_value:
            return None

        if isinstance(schedule_value, str):
            schedule_text = schedule_value.strip()

            if ':' in schedule_text:
                parts = schedule_text.split(':')
                if len(parts) == 2:
                    try:
                        hour = int(parts[0])
                        minute = int(parts[1])
                        if 0 <= hour <= 23 and 0 <= minute <= 59:
                            return hour, minute
                    except ValueError:
                        return None

            fields = schedule_text.split()
            if len(fields) >= 2:
                try:
                    minute = int(fields[0])
                    hour = int(fields[1])
                    if 0 <= hour <= 23 and 0 <= minute <= 59:
                        return hour, minute
                except ValueError:
                    return None

        return None

    def _describe_cron(self, cron_expression):
        """
        Generate human-readable description of cron expression
        
        Args:
            cron_expression (str): Cron expression (5 parts)
            
        Returns:
            str: Human-readable description
        """
        try:
            parts = cron_expression.split()
            if len(parts) != 5:
                return cron_expression
            
            minute, hour, day_of_month, month, day_of_week = parts
            
            description = ''
            
            # Time
            if hour != '*' and minute != '*':
                description += f'At {hour.zfill(2)}:{minute.zfill(2)}'
            
            # Day of week
            if day_of_week != '*':
                days = {
                    '0': 'Sunday', '1': 'Monday', '2': 'Tuesday',
                    '3': 'Wednesday', '4': 'Thursday', '5': 'Friday', '6': 'Saturday'
                }
                
                if '-' in day_of_week:
                    start, end = day_of_week.split('-')
                    description += f' on {days.get(start, start)}-{days.get(end, end)}'
                elif ',' in day_of_week:
                    day_names = [days.get(d, d) for d in day_of_week.split(',')]
                    description += f' on {", ".join(day_names)}'
                else:
                    description += f' on {days.get(day_of_week, day_of_week)}'
            
            return description if description else cron_expression
        
        except:
            return cron_expression
    
    def get_scheduled_jobs(self):
        """
        Get list of scheduled jobs
        
        Returns:
            list: List of job information dictionaries
        """
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'name': job.name,
                'next_run': job.next_run_time.isoformat() if job.next_run_time else None
            })
        return jobs
