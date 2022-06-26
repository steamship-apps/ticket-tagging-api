# Ticket Tagging API

The goal of this app is to automatically assign labels or tags support-system tickets as they come in.  The app assumes
your data will be held elsewhere, and the API provided will be used to tag the tickets as they come in.

The app allows you to begin tagging tickets immediately with no training, leveraging zero-shot classification.  If you wish
to improve performance, you can provide examples of text and labels, and transition to using a likely higher-accuracy 
trained model.  

## Parameters

- **save_classifications** - Whether to retain all classifications in the Steamship Space for caching or analysis purposes.

## Endpoints

- **set_labels** (List[labels]) - Set the labels that will be used for tagging.  This can be a simple list of strings. Resetting the labels after training a model will reset to zero-shot classification.  For best results, clean labels of special characters like underscores.
- **tag_ticket**( ticket_text ) - Tag a ticket.  Returns confidences for all provided labels.  Throws an error if set_labels has not been called.  This method will work out of the box with a zero-shot classifier, and will seamlessly transition to a trained model after prerequisites are met below.
- **add_example** (ticket_text, list[labels]) - Add a curated example for learning.  This could happen after a user manually confirms or rejects ticket suggestions, or when importing an existing set of pre-tagged tickets.  One call per ticket, or we could provide a batch interface.
- **count_examples**() - Return both total count and count per tag of the examples that have been added so far.
- **start_specialize**() - When sufficient data has been loaded, call this to switch from zero-shot to trained classifiers for better performance.
- **specialize_status**() - Call this to know the current status of the app: unspecialized, specialization_in_progress, or specialized.  This method *must* be polled after specialization begins for the app to switch to specialized mode.
- **clear_examples**() - Remove all previously added examples
- **evaluate()** - [not yet implemented] Compare performance of labeled tickets to added examples, watch for drift over time

## Full Example

Full examples of usage are located as Jupyter notebooks in [example/](example/)

## Developing

Instructions for contributing to this project are located in [DEVELOPING.md](DEVELOPING.md)

## Testing

Instructions for testing this project are located in [TESTING.md](TESTING.md)

## Deploying

Instructions for deploying this project are located in [DEPLOYING.md](DEPLOYING.md)
