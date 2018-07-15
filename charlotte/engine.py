import json
import logging

import redis
from jsonschema import validate

from charlotte.errors import CharlotteConfigurationError
from charlotte.errors import CharlotteConnectionError

# we don't actually connect to redis until we use the object; putting it here
# means that we have the connection pool available if we need it.
pool = redis.ConnectionPool(host="localhost", port=6379, db=0)


class Base(object):
    """
    Welcome to the weirdness that is Charlotte.

    Charlotte is a ODM that specializes in all things json, because
    frankly I really don't like working with ORMs and the way that they're
    normally handled in Python (thanks, Django!).

    It's very simple: you create a class using a minimum of two objects:

      * A dict of what you want your data to look like
      * a dict of valid jsonschema that will be used to validate your data
          on save

    That's it. No models, no craziness, minor setup time, and hopefully pretty
    simple to use. That's the goal, anyways.

    Why Charlotte? I like Charlotte best. Because it's good. Good Charlotte.
    """

    def __init__(self, id):
        """
        Everything that we should need is passed in by the user and found
        under the `self` object. Here's what we should be seeing:

        class User(Prototype):
            default_structure = {valid dict}

            # optional flags
            schema = {valid jsonschema}
            redis_object = r
            redis_key = "user-obj"

        The schema is technically optional, but we want people to use it.
        Because the user creates the class with those variables defined,
        we can structure the parent around them. Fun!
        """
        try:
            if hasattr(self, "redis_conn"):
                # We have something -- we'll run it through the same testing code to
                # make sure that it works.
                self.r = self.redis_conn
            else:
                self.r = redis.Redis(connection_pool=pool)
            self.r.ping()
        except redis.exceptions.ConnectionError:
            raise CharlotteConnectionError("Unable to reach Redis.")
        except Exception as e:
            raise CharlotteConfigurationError(
                "Caught {} -- please pass in an instantiated Redis connection.".format(
                    e
                )
            )

        if not hasattr(self, "default_structure"):
            raise CharlotteConfigurationError(
                "Must have a default_structure dict, even if it's just {}!"
            )
        if type(self.default_structure) != dict:
            raise CharlotteConfigurationError("default_structure must be a dict!")

        if not hasattr(self, "redis_key"):
            # if we don't have a redis_key passed in, then we use the name of the
            # class that the developer defined as the key.
            self.redis_key = self.__class__.__name__.lower()
        else:
            self.redis_key = str(self.redis_key)
        # note: this is a way of allowing us to only format the first field.
        # It'll render out as "::thing::{}" which we can then format again.
        self.redis_key = "::{}::{{}}".format(self.redis_key)

        if not hasattr(self, "schema"):
            self.schema = None

        self.id = id

        result = self._load(self.id)
        if result:
            self.data = result
        else:
            self.data = self.default_structure

    def __repr__(self):
        return repr(self.data)

    def __len__(self):
        return len(self.data)

    def __getitem__(self, item):
        return self.data[item]

    def __setitem__(self, key, value):
        self.data[key] = value

    def get(self, key, default_return=None):
        return self.data.get(key, default_return)

    def _load(self, requested_key):
        """
        :return: Dict or None; the loaded information from Redis.
        """
        result = self.r.get(self.redis_key.format(requested_key))
        if not result:
            logging.debug("Key {} not found, returning None.".format(requested_key))
            return None

        return json.loads(result.decode())

    def save(self):
        if self.validate():
            self.r.set(self.redis_key.format(self.id), json.dumps(self.data))

    def update(self, key, value):
        self.data[key] = value

    def to_dict(self):
        return self.data

    def validate(self):
        # validate will return None if it succeeds or throw an exception, so if
        # we get to the return statement then we're good.
        # Alternatively, they can just not give us a schema -- in which case,
        # just return True and don't sweat it.
        if self.schema:
            validate(self.data, self.schema)
        return True
