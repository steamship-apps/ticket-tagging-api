from enum import Enum
from typing import Dict, Any
from steamship import Steamship, PluginInstance, Block, Tag, File, SteamshipError
from steamship.app import App, Response, post, create_handler
import json
import os

from steamship.base import TaskState
from steamship.data.operations.tagger import TagResponse
from steamship.plugin.inputs.export_plugin_input import ExportPluginInput
from steamship.plugin.inputs.training_parameter_plugin_input import TrainingParameterPluginInput
from steamship.base.response import Response as BaseResponse
from steamship.plugin.outputs.train_plugin_output import TrainPluginOutput

#This is necessary because the project's package structure (beginning with src) does not match the deployed
#app's package structure (beginning in the root namespace).  To change it, the project files should probably be moved up
#a level, but an appropriate engine change must be made.
try:
  from resources import config_json
except:
  from src.resources import config_json


class TicketTaggingApp(App):

  zero_shot_classifier_plugin_instance_handle = 'zero-shot-classifier-handle'
  trained_classifier_plugin_instance_handle = 'trained-classifier-handle'
  tag_kind = 'ticket-tag'

  zero_shot_classifier : PluginInstance = None
  trained_classifier : PluginInstance = None

  save_classifications : bool = True

  def __init__(self, client: Steamship, config: Dict[str, Any] = None):
    super().__init__(client, config)

    self.plugins_config = config_json()
    self.save_classifications = config['save_classifications']

    #It's ok if this doesn't exist yet upon init.
    try:
      self.zero_shot_classifier = PluginInstance.get(client, handle=self.zero_shot_classifier_plugin_instance_handle).data
    except:
       # It's ok if this doesn't exist yet upon init.
       pass
    try:
      self.trained_classifier = PluginInstance.get(client, handle=self.trained_classifier_plugin_instance_handle).data
    except:
      # It's ok if this doesn't exist yet upon init.
      pass




  def _get_active_plugin(self):
    status, _ = self._get_specialization_status()
    if status == TicketTaggingApp.SpecializationStatus.SPECIALIZED:
      return self.trained_classifier
    elif self.zero_shot_classifier is not None:
      return self.zero_shot_classifier
    else:
      return None

  class SpecializationStatus(Enum):
    UNSPECIALIZED='unspecialized'
    SPECIALIZED='specialized'
    SPECIALIZATION_IN_PROGRESS='specialization_in_progress'

  def _get_specialization_status(self) -> (SpecializationStatus, dict):
    status_files = File.query(self.client, 'filetag and kind "specialization_status"').data.files
    if len(status_files) == 0:
      return (TicketTaggingApp.SpecializationStatus.UNSPECIALIZED, None)
    status_tag = status_files[0].tags[0]
    if status_tag.value['status'] == 'training':
      return (TicketTaggingApp.SpecializationStatus.SPECIALIZATION_IN_PROGRESS, status_tag.value['response'])
    else:
      return (TicketTaggingApp.SpecializationStatus.SPECIALIZED, None)

  def _remove_status(self):
    # Remove any leftover status from previous runs;
    status_files = File.query(self.client, 'filetag and kind "specialization_status"').data.files
    for file in status_files:
      # this shouldn't be necessary
      file.client = self.client
      file.delete()


  def _get_current_labels(self) -> [str]:
      return self.zero_shot_classifier.config['labels'].split(',')

  @post('set_labels')
  def set_labels(self, labels: [str]) -> Response:
    plugin_config = self.plugins_config['zero_shot_config']
    plugin_config['labels'] = ','.join(labels)
    plugin_config['multi_label'] = True
    plugin_config['tag_kind'] = self.tag_kind
    plugin_config['use_gpu'] = True

    if self.zero_shot_classifier is not None:
      self.zero_shot_classifier.delete()

    if self.trained_classifier is not None:
      self.trained_classifier.delete()

    self.zero_shot_classifier = PluginInstance.create(self.client, handle=self.zero_shot_classifier_plugin_instance_handle,
                                                      plugin_handle='tagger-zero-shot-class-hf-bart-mnli', config=plugin_config).data

    return Response(string="Labels accepted")


  @post('tag_ticket')
  def tag_ticket(self, ticket_text: str = None) -> Response:
    plugin_to_use = self._get_active_plugin()
    if plugin_to_use is None:
      return Response(error=SteamshipError(message='Could not tag ticket; no classifier plugin initialized',
                                    suggestion='Have you called set_labels yet?'))

    response = plugin_to_use.tag(ticket_text)
    response.wait()
    result = {tag.name : (tag.value['score'] if 'score' in tag.value else tag.value['confidence']) for tag in response.data.file.blocks[0].tags }
    return Response(json=result)


  @post('add_example')
  def add_example(self, ticket_text: str, labels: [str]) -> Response:
    tags = [Tag.CreateRequest(kind=self.tag_kind, name=label, value={'asserted':True}) for label in labels]
    file = File.create(self.client, blocks=[Block.CreateRequest(text=ticket_text, tags=tags)]).data
    if file is not None:
      return Response(string='Example accepted')
    else:
      return Response(error=SteamshipError(message='Could not add example'))

  @post('count_examples')
  def count_examples(self) -> Response:
    labels = self._get_current_labels()
    total_examples = len(File.query(self.client, f'blocktag and kind "{self.tag_kind}" and value("asserted") = true').data.files)
    result = dict(total_examples=total_examples)
    label_examples = {}
    for label in labels:
      num_label_examples = len(File.query(self.client, tag_filter_query=f'name "{label}"').data.files)
      label_examples[label] = num_label_examples
    result['label_examples'] = label_examples
    return Response(json=result)

  @post('start_specialize')
  def start_specialize(self) -> Response:
    trainable_plugin_config = self.plugins_config['trainable_config']

    trainable_plugin_config['single_or_multi_label'] = "multi"
    trainable_plugin_config['tag_kind'] = self.tag_kind
    trainable_plugin_config['include_tag_names'] = ','.join(self._get_current_labels())

    self.trained_classifier = PluginInstance.create(self.client, handle=self.trained_classifier_plugin_instance_handle,
                                            plugin_handle='tagger-trainable-classifier-gcp-vertexai',
                                           config=trainable_plugin_config).data
    exporter = PluginInstance.get(self.client, handle='signed-url-exporter-1.0').data
    training_request = TrainingParameterPluginInput(
      plugin_instance=self.trained_classifier.handle,
      export_plugin_input=ExportPluginInput(
        plugin_instance=exporter.handle, type="file", query='blocktag and value("asserted") = true',
      ),
      training_params={},
    )
    train_response = self.trained_classifier.train(training_request)

    self._remove_status()
    response_dict = train_response.dict(exclude={'client', 'expect'})
    File.create(self.client, blocks=[Block.CreateRequest(text='')], tags=[Tag.CreateRequest(kind='specialization_status', name='', value={'response':response_dict, 'status':'training'})])

    return Response(string="Started specialization. Please poll specialize_status")



  @post('specialize_status')
  def specialize_status(self)  -> Response:
    status, response = self._get_specialization_status()
    if status == TicketTaggingApp.SpecializationStatus.SPECIALIZATION_IN_PROGRESS:
      response_object = BaseResponse.parse_obj(response)
      response_object.client = self.client
      response_object.refresh()
      if response_object.task.state == TaskState.succeeded:
        #SWITCH TO SPECIALIZED
        self._remove_status()
        File.create(self.client, blocks=[Block.CreateRequest(text='')], tags=[Tag.CreateRequest(kind='specialization_status', name='',
                                                         value={'status': 'trained'})])

      elif response_object.task.state == TaskState.failed:
        #switch to unspecialized; something went wrong
        self._remove_status()
        return Response(json={'status': TicketTaggingApp.SpecializationStatus.UNSPECIALIZED.name, 'message':response_object.task.status_message})
      else:
        return Response(json={'status':status.name})
    else:
      return Response(json={'status':status.name})


  @post('clear_examples')
  def clear_examples(self) -> Response:
    example_files = File.query(self.client, f'blocktag and kind "{self.tag_kind}" and value("asserted") = true').data.files
    count = 0
    for file in example_files:
      # This shouldn't be necessary
      file.client = self.client
      file.delete()
      count += 1
    return Response(string=f'Removed {count} examples')

handler = create_handler(TicketTaggingApp)



