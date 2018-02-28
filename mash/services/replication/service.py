# Copyright (c) 2018 SUSE Linux GmbH.  All rights reserved.
#
# This file is part of mash.
#
# mash is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# mash is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with mash.  If not, see <http://www.gnu.org/licenses/>
#

import json
import os

from amqpstorm import AMQPError

from apscheduler import events
from apscheduler.jobstores.base import ConflictingIdError, JobLookupError
from apscheduler.schedulers.background import BackgroundScheduler

from mash.services.base_service import BaseService
from mash.services.status_levels import EXCEPTION, SUCCESS
from mash.services.replication.config import ReplicationConfig
from mash.services.replication.ec2_job import EC2ReplicationJob


class ReplicationService(BaseService):
    """
    Implementation of replication service.

    Handles the replication of images in public cloud providers.
    """

    def post_init(self):
        """
        Initialize replication service class.
        """
        self.config = ReplicationConfig()
        self.set_logfile(self.config.get_log_file(self.service_exchange))

        self.jobs = {}

        self.bind_credentials_queue()

        self.scheduler = BackgroundScheduler()
        self.scheduler.add_listener(
            self._process_replication_result,
            events.EVENT_JOB_EXECUTED | events.EVENT_JOB_ERROR
        )

        self.restart_jobs(self._add_job)
        self.start()

    def _add_job(self, job_config):
        """
        Add new job to replication queue from job_config.
        """
        job_id = job_config['id']
        provider = job_config['provider']

        if job_id in self.jobs:
            self.log.warning(
                'Job already queued.',
                extra={'job_id': job_id}
            )
        elif provider == 'EC2':
            self._create_job(EC2ReplicationJob, job_config)
        else:
            self.log.exception(
                'Provider {0} is not supported.'.format(provider)
            )

    def _cleanup_job(self, job, status):
        """
        Job failed upstream.

        Delete job and notify the pint service.
        """
        job.status = status
        self.log.warning('Failed upstream.', extra=job.get_metadata())

        self._delete_job(job.id)
        self._publish_message(job)

    def _create_job(self, job_class, job_config):
        """
        Create an instance of job_class with the given config.

        If successful:
        1. Add to jobs queue.
        2. Configure the job.
        3. Store config file if not stored already.
        4. Bind to job listener queue.
        """
        try:
            job = job_class(**job_config)
        except Exception as e:
            self.log.exception(
                'Invalid job configuration: {0}'.format(e)
            )
        else:
            self.jobs[job.id] = job
            job.set_log_callback(self._log_job_message)

            if 'job_file' not in job_config:
                job_config['job_file'] = self.persist_job_config(
                    job_config
                )
                job.job_file = job_config['job_file']

            self.bind_listener_queue(job.id)
            self.log.info(
                'Job queued, awaiting testing result.',
                extra=job.get_metadata()
            )

    def _delete_job(self, job_id):
        """
        Remove job from dict and delete listener queue.
        """
        if job_id in self.jobs:
            try:
                # Remove job from scheduler if it has
                # not started executing yet.
                self.scheduler.remove_job(job_id)
            except JobLookupError:
                pass

            job = self.jobs[job_id]
            self.log.info(
                'Deleting job.',
                extra=job.get_metadata()
            )

            del self.jobs[job_id]
            self.unbind_queue(
                self.listener_queue, self.service_exchange, job_id
            )
            self._remove_job_config(job.job_file)
        else:
            self.log.warning(
                'Job deletion failed, job is not queued.',
                extra={'job_id': job_id}
            )

    def _get_status_message(self, job):
        """
        Build and return json message.

        Message contiains completion status to post to service exchange.
        """
        if job.status == SUCCESS:
            data = {
                'replication_result': {
                    'id': job.id,
                    'cloud_image_name': job.cloud_image_name,
                    'source_regions': job.get_source_regions_result(),
                    'status': job.status,
                }
            }
        else:
            data = {
                'replication_result': {
                    'id': job.id,
                    'status': job.status,
                }
            }

        return json.dumps(data, sort_keys=True)

    def _handle_credentials_response(self, message):
        """
        Process credentials response JWT tokens.
        """
        token = json.loads(message.body)
        payload = self.decode_credentials(token['jwt_token'])
        job = self.jobs.get(payload['id'])

        job.credentials = payload['credentials']
        self._schedule_job(job.id)

        message.ack()

    def _handle_listener_message(self, message):
        """
        Process incoming listener messages for queued jobs.

        {
            "testing_result": {
                "id": "1",
                "image_id": "ami-2c40774c",
                "image_name": "test_image",
                "status": "success"
            }
        }

        If message is valid initiate replication of image in new thread.
        """
        job = self._validate_listener_msg(message.body)

        if job:
            job.listener_msg = message

            if job.credentials:
                self._schedule_job(job.id)
            else:
                self.publish_credentials_request(job.id)
        else:
            message.ack()

    def _handle_service_message(self, message):
        """
        Process incoming service events with new jobs.

        If message is valid create instance of replication and
        queue the job.

        job_config example:
        {
            "replication_job": {
                "account": "account",
                "id": "1",
                "provider": "EC2",
                "utctime": "now"
            }
        }
        """
        try:
            job_desc = json.loads(message.body)
        except ValueError as error:
            self.log.error('Invalid job config file: {0}.'.format(error))
            self.notify_invalid_config(message.body)
        else:
            if 'replication_job' in job_desc:
                if not self._validate_job_config(job_desc['replication_job']):
                    self.notify_invalid_config(message.body)
                else:
                    self._add_job(job_desc['replication_job'])
            else:
                self.log.error(
                    'Invalid replication job: Job document must contain '
                    'the replication_job key.'
                )
                self.notify_invalid_config(message.body)

        message.ack()

    def _log_job_message(self, msg, metadata, success=True):
        """
        Callback for job instance to log given message.
        """
        if success:
            self.log.info(msg, extra=metadata)
        else:
            self.log.warning(msg, extra=metadata)

    def _process_replication_result(self, event):
        """
        Callback when replication background process finishes.

        Handle exceptions and errors that occur during replication and
        logs info to job log.
        """
        job_id = event.job_id
        job = self.jobs[job_id]
        metata = job.get_metadata()

        if job.utctime != 'always':
            self._delete_job(job_id)

        if event.exception:
            job.status = EXCEPTION
            self.log.error(
                'Pass[{0}]: Exception replicating image: {1}'.format(
                    job.iteration_count,
                    event.exception
                ),
                extra=metata
            )
        elif job.status == SUCCESS:
            self.log.info(
                'Pass[{0}]: Publishing successful.'.format(
                    job.iteration_count
                ),
                extra=metata
            )
        else:
            self.log.error(
                'Pass[{0}]: Error occurred replicating image.'.format(
                    job.iteration_count
                ),
                extra=metata
            )

        if job.utctime != 'always' or job.status == SUCCESS:
            self._publish_message(job)
        job.listener_msg.ack()

    def _replicate_image(self, job_id):
        """
        Publish image for job that matches job_id
        """
        job = self.jobs[job_id]
        job.replicate_image(host=self.host)

    def _publish_message(self, job):
        """
        Publish status message to publish service.
        """
        message = self._get_status_message(job)

        try:
            self.publish_job_result('publisher', job.id, message)
        except AMQPError:
            self.log.warning(
                'Message not received: {0}'.format(message),
                extra=job.get_metadata()
            )

    def _remove_job_config(self, job_file):
        """
        Remove job config file from disk if it exists.
        """
        try:
            os.remove(job_file)
        except Exception:
            pass

    def _schedule_job(self, job_id):
        """
        Schedule new job in background scheduler for job based on id.
        """
        try:
            self.scheduler.add_job(
                self._replicate_image,
                args=(job_id,),
                id=job_id,
                max_instances=1,
                misfire_grace_time=None,
                coalesce=True
            )
        except ConflictingIdError:
            self.log.warning(
                'Replication job already running. Received multiple '
                'listener messages.',
                extra={'job_id': job_id}
            )

    def _validate_job_config(self, job_config):
        """
        Validate the job has the required attributes.
        """
        required = [
            'id', 'image_description', 'provider', 'utctime', 'source_regions'
        ]
        for attr in required:
            if attr not in job_config:
                self.log.error(
                    '{0} is required in replication job config.'.format(attr)
                )
                return False
        return True

    def _validate_listener_msg(self, message):
        """
        Validate the required keys are in message dictionary.

        If listener message is valid return the job instance.
        """
        try:
            listener_msg = json.loads(message)['testing_result']
        except Exception:
            self.log.error(
                'Invalid testing result file: {0}'.format(message)
            )
            return None

        job_id = listener_msg.get('id')
        status = listener_msg.get('status')

        if not job_id:
            self.log.error('id is required in testing result.')
            return None

        job = self.jobs.get(job_id)
        if not job:
            self.log.error(
                'Invalid replication service job with id: {0}.'.format(job_id)
            )
            return None
        elif status != SUCCESS:
            self._cleanup_job(job, status)
            return None
        else:
            # Required args
            for attr in ['image_id', 'image_name', 'source_region']:
                if attr not in listener_msg:
                    self.log.error(
                        '{0} is required in testing result.'.format(attr)
                    )
                    return None
                else:
                    setattr(job, attr, listener_msg[attr])

            # Optional args
            for attr in ['image_description', 'regions']:
                if attr in listener_msg:
                    setattr(job, attr, listener_msg[attr])

        return job

    def start(self):
        """
        Start replication service.
        """
        self.scheduler.start()
        self.consume_queue(self._handle_service_message)
        self.consume_queue(
            self._handle_listener_message, queue_name=self.listener_queue
        )
        self.consume_credentials_queue(self._handle_credentials_response)
        try:
            self.channel.start_consuming()
        except KeyboardInterrupt:
            pass
        except Exception:
            raise
        finally:
            self.stop()

    def stop(self):
        """
        Stop replication service.

        Stop consuming queues and close pika connections.
        """
        self.scheduler.shutdown()
        self.channel.stop_consuming()
        self.close_connection()
