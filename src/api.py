from typing import Dict
from steamship import Steamship, PluginInstance, Block, Tag, File, SteamshipError
from steamship.app import App, Response, post, create_handler
import json
import os
from steamship.data.operations.tagger import TagResponse
from steamship.plugin.inputs.export_plugin_input import ExportPluginInput
from steamship.plugin.inputs.training_parameter_plugin_input import TrainingParameterPluginInput


class TicketTaggingApp(App):

  zero_shot_classifier_plugin_instance_handle = 'zero-shot-classifier-handle'
  trained_classifier_plugin_instance_handle = 'trained-classifier-handle'
  tag_kind = 'ticket-tag'

  zero_shot_classifier : PluginInstance = None
  trained_classifier : PluginInstance = None

  def __init__(self, client: Steamship):
    super().__init__(client)
    folder = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(folder, 'config.json')) as config_file:
      self.plugins_config = json.load(config_file)

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
    if self.trained_classifier is not None:
      return self.trained_classifier
    elif self.zero_shot_classifier is not None:
      return self.zero_shot_classifier
    else:
      return None

  def _get_current_labels(self) -> [str]:
      return self.zero_shot_classifier.config['labels'].split(',')

  @post('set_labels')
  def set_labels(self, labels: [str]) -> Response:
    plugin_config = self.plugins_config['zero_shot_config']
    plugin_config['labels'] = ','.join(labels)
    plugin_config['multi_label'] = True
    plugin_config['tag_kind'] = self.tag_kind

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
    result = {tag.name : tag.value['score'] for tag in response.data.file.blocks[0].tags }
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
    total_examples = len(File.list(self.client).data.files)
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

    self.trained_classifier = PluginInstance.create(self.client, plugin_handle='tagger-trainable-classifier-gcp-vertexai',
                                           config=trainable_plugin_config).data
    exporter = PluginInstance.get(self.client, handle='signed-url-exporter-1.0').data
    training_request = TrainingParameterPluginInput(
      plugin_instance=self.trained_classifier.handle,
      export_plugin_input=ExportPluginInput(
        plugin_instance=exporter.handle, type="file", query="blocktag",
      ),
      training_params={},
    )
    train_result = self.trained_classifier.train(training_request)

handler = create_handler(TicketTaggingApp)



