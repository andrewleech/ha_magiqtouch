from mandate.utils import cognito_to_dict


class UserObj(object):

    def __init__(self, username, attribute_list, cognito_obj,
                 metadata=None, attr_map=None):
        """
        :param username:
        :param attribute_list:
        :param metadata: Dictionary of User metadata
        """
        self.username = username
        self.pk = username
        self._cognito = cognito_obj
        self._attr_map = {} if attr_map is None else attr_map
        self._data = cognito_to_dict(attribute_list, self._attr_map)
        self.sub = self._data.pop('sub', None)
        self.email_verified = self._data.pop('email_verified', None)
        self.phone_number_verified = self._data.pop(
            'phone_number_verified', None)
        self._metadata = {} if metadata is None else metadata

    def __repr__(self):
        return '<{class_name}: {uni}>'.format(
            class_name=self.__class__.__name__, uni=self.__unicode__())

    def __unicode__(self):
        return self.username

    def __getattr__(self, name):
        if name in list(self.__dict__.get('_data', {}).keys()):
            return self._data.get(name)
        if name in list(self.__dict__.get('_metadata', {}).keys()):
            return self._metadata.get(name)

    def __setattr__(self, name, value):
        if name in list(self.__dict__.get('_data', {}).keys()):
            self._data[name] = value
        else:
            super(UserObj, self).__setattr__(name, value)

    def save(self, admin=False):
        if admin:
            self._cognito.admin_update_profile(self._data, self._attr_map)
            return
        self._cognito.update_profile(self._data, self._attr_map)

    def delete(self, admin=False):
        if admin:
            self._cognito.admin_delete_user()
            return
        self._cognito.delete_user()
