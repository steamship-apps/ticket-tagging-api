from enum import Enum
from typing import Dict, Any, Optional
from steamship import Steamship, PluginInstance, Block, Tag, File, SteamshipError
from steamship.app import App, Response, post, create_handler
import datetime
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


class KeyValueStore:
  """A simple key value store hacked into Steamship.

  Each entry is stored as an empty file whose "Key" has:
    * Kind = KeyValueStore
    * Name = the key of the (kv) pair
    * Value = a dict set to the value
  """

  client: Steamship
  namespace: str

  def __init__(self, client: Steamship, namespace: str = "KeyValueStore"):
    self.client = client
    self.namespace = namespace

  def _get_file(self, or_create: bool = False) -> Optional[File]:
    status_files = File.query(self.client, f'filetag and kind "{self.namespace}"').data.files
    if len(status_files) == 0:
      if not or_create:
        return None
      return File.create(
        self.client,
        blocks=[Block.CreateRequest(text='')],
        tags=[Tag.CreateRequest(kind=self.namespace, name='__init__')]
      ).data
    else:
      return status_files[0]

  def get(self, key: str) -> Optional[Dict]:
    """Gets the value represented by `key`."""
    file = self._get_file()

    if file is None:
      return None

    for tag in file.tags:
      if tag.kind == self.namespace and tag.name == key:
        return tag.value

  def delete(self, key: str) -> bool:
    """Deletes the entry represented by `key`"""
    file = self._get_file()

    if file is None:
      return False

    deleted = False
    for tag in file.tags:
      if tag.kind == self.namespace and tag.name == key:
        tag.delete()

    return deleted

  def set(self, key: str, value: Dict[str, Any]):
    # Sets the entry (key, value)

    # First delete it if it exists to avoid duplicate tags.
    self.delete(key)

    # Now get/create the file
    file = self._get_file(or_create = True)

    req = Tag.CreateRequest(
      file_id=file.id,
      kind=self.namespace,
      name=key,
      value=value
    )
    return self.client.post("tag/create", req, expect=Tag)

  def reset(self):
    """Deletes all keys"""
    file = self._get_file()
    if file is not None:
      file.delete()


class TicketTaggingApp(App):

  zero_shot_classifier_plugin_instance_handle = 'zero-shot-classifier-handle'
  trained_classifier_plugin_instance_handle = 'trained-classifier-handle'
  tag_kind = 'ticket-tag'

  kvstore: KeyValueStore = None

  zero_shot_classifier : PluginInstance = None
  trained_classifier : PluginInstance = None

  save_classifications : bool = True


  def __init__(self, client: Steamship, config: Dict[str, Any] = None):
    super().__init__(client, config)

    self.plugins_config = config_json()
    self.save_classifications = config['save_classifications']
    self.kvstore = KeyValueStore(client=client)

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

  STATUS_KEY = 'specialization_status'
  STATUS_SUB_KEY = 'status'
  RESPONSE_SUB_KEY = 'response'

  class SpecializationStatus(Enum):
    """These are for use with the """
    UNSPECIALIZED='unspecialized'
    SPECIALIZED='specialized'
    PREPARING ='specialization_in_progress:preparing' # Preparing dataset
    TRAINING ='specialization_in_progress:training'   # Training
    DEPLOYING ='specialization_in_progress:deploying' # Deploying


  def _get_specialization_status(self) -> (SpecializationStatus, dict):
    """Returns the current specialization status"""
    status_obj = self.kvstore.get(TicketTaggingApp.STATUS_KEY)
    if status_obj is None:
      return (TicketTaggingApp.SpecializationStatus.UNSPECIALIZED, None)
    else:
      return (
        status_obj.get(TicketTaggingApp.STATUS_SUB_KEY, None),
        status_obj.get(TicketTaggingApp.RESULT_SUB_KEY, None)
      )

  def _remove_status(self):
    # Remove any leftover status from previous runs;
    self.kvstore.reset()

  def _set_specialization_status(self, status: SpecializationStatus, response: dict):
    self.kvstore.set(TicketTaggingApp.STATUS_KEY, {
      TicketTaggingApp.STATUS_SUB_KEY: status,
      TicketTaggingApp.RESPONSE_SUB_KEY: response
    })

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

    if self.save_classifications:
      file : File = File.create(
        self.client,
        blocks=[Block.CreateRequest(text=ticket_text)],
        tags=[Tag.CreateRequest(kind='metadata', name='metadata', value={"creation_datetime":f"{datetime.datetime.now().isoformat()}"})]
      ).data
      response = file.tag(plugin_instance=plugin_to_use.handle)
    else:
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
      num_label_examples = len(File.query(self.client, tag_filter_query=f'kind "{self.tag_kind}" and name "{label}" and value("asserted") = true').data.files)
      label_examples[label] = num_label_examples
    result['label_examples'] = label_examples
    return Response(json=result)

  @post('clear_trained_model')
  def clear_trained_model(self) -> Response:
    self.kvstore.reset()
    if self.trained_classifier is not None:
      self.trained_classifier.delete()
    return Response(string="OK")

  @post('start_specialize')
  def start_specialize(self) -> Response:
    # If we're already specializing, then fail.
    (init_status, init_response) = self._get_specialization_status()
    if init_status != TicketTaggingApp.SpecializationStatus.UNSPECIALIZED:
      raise SteamshipError(message=f"Can not start specialization because specialization has already been started. Current status is {init_status}. Please POST to /clear_trained_model first.")

    # If we're still here, we're ready to start.
    trainable_plugin_config = self.plugins_config['trainable_config']
    trainable_plugin_config['single_or_multi_label'] = "multi"
    trainable_plugin_config['tag_kind'] = self.tag_kind
    trainable_plugin_config['include_tag_names'] = ','.join(self._get_current_labels())

    if self.trained_classifier is not None:
      self.trained_classifier.delete()

    self.trained_classifier = PluginInstance.create(self.client, handle=self.trained_classifier_plugin_instance_handle,
                                            plugin_handle='tagger-trainable-classifier-gcp-vertexai',
                                           config=trainable_plugin_config).data
    exporter = PluginInstance.get(self.client, handle='signed-url-exporter-1.0').data
    training_request = TrainingParameterPluginInput(
      plugin_instance=self.trained_classifier.handle,
      export_plugin_input=ExportPluginInput(
        plugin_instance=exporter.handle, type="file", query=f'blocktag and kind "{self.tag_kind}" and value("asserted") = true',
      ),
      training_params={},
    )
    train_response = self.trained_classifier.train(training_request)
    response_dict = train_response.dict(exclude={'client', 'expect'})
    self._set_specialization_status(TicketTaggingApp.SpecializationStatus.PREPARING, response_dict)
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
        return Response(json={'status': TicketTaggingApp.SpecializationStatus.SPECIALIZED.name})
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



