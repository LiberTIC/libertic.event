#!/usr/bin/env python
# -*- coding: utf-8 -*-
__docformat__ = 'restructuredtext en'
from five import grok
import datetime
import socket
import time
try:
    import json
except ImportError:
    from simplejson import json

from zope.schema.fieldproperty import FieldProperty
from zope import schema
from zope.interface import implements, alsoProvides, Interface, implementedBy
from z3c.form.interfaces import ActionExecutionError
from zope.component import getUtility

from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from Products.CMFCore.utils import getToolByName
from Products.CMFCore.utils import getToolByName
from Products.ATContentTypes.interfaces.topic import IATTopic
from pprint import pformat

from plone.directives import form, dexterity
from plone.app.collection.interfaces import ICollection
from plone.dexterity.utils import createContent


from libertic.event.content.liberticevent import export_csv
from plone.dexterity.utils import createContentInContainer
from libertic.event.content import source
from libertic.event import interfaces as i
from libertic.event.content.source import Source, Log
from libertic.event.content.liberticevent import (
    data_from_ctx,
    empty_data,
    LiberticEvent,
    unique_SID_EID_check,
    editable_SID_EID_check,
)
from libertic.event.utils import Browser

_marker = object()
class NotUnique(Exception):pass
class CantEdit(Exception):pass

class SourceMapping(object):
    implements(i.ISourceMapping)
    eid = FieldProperty(i.ISourceMapping['eid'])
    sid = FieldProperty(i.ISourceMapping['sid'])
    def __init__(self, sid=None, eid=None):
        self.sid = sid
        self.eid = eid

class Dummy(object):
    """Dummy object with arbitrary attributes
    """
    def __init__(self, **kw):
        self.__dict__.update(kw)



    @property
    def title(self):
        return '%s_%s' % (
            self.sid, self.eid
        )



class DBPusher(grok.Adapter):
    grok.context(i.IDatabase)
    grok.provides(i.IDBPusher)
    def push_event(self, data):
        db = self.context
        status = 'failed'
        messages = []
        event = None
        if data['errors']:
            msg = "A record failed validation: \n"
            try:
                msg += "%s\n"% pformat(data["initial"])
            except Exception, e:
                msg += "\n"
            for it in data["errors"]:
                msg += "%s\n" % it
            messages.append(msg)
        else:
            # relations are done later to avoid circular dependencies errors
            cdata = data.copy()
            for k in ['contained', 'related']:
                if k in cdata:
                    del cdata[k]
            # to create an event,
            # verify that there are no ther event with same (eid, sid)
            try:
                try:
                    constructor = i.IEventConstructor(db)
                    event = constructor.construct(data['transformed'])
                    status = 'created'
                except NotUnique, e:
                    # in case of not unique, it means an edit session
                    editor = i.IEventEditor(db)
                    event = editor.edit(data['transformed'])
                    status = 'edited'
            except Exception, e:
                status = 'failed'
                try:
                    messages.append(
                        "Failed to push event: \n%s\n%s" % (e, pformat(data)))
                except Exception, e:
                    # handle case where repr(data) can failed
                    messages.append("%s" % e)
        return messages, status, event


class EventsImporter(grok.Adapter):
    grok.context(i.ISource)
    grok.provides(i.IEventsImporter)
    def do_import(self, *args, **kwargs):
        """Here datas is mainly used for tests"""
        messages = []
        catalog = getToolByName(self.context, 'portal_catalog')
        status = 1
        created, edited, failed = 0, 0, 0
        try:
            if not self.context.activated:
                raise Exception('This source is not activated')
            grabber = getUtility(i.IEventsGrabber, name=self.context.type)
            datas = grabber.data(self.context.source)
            db = i.IDatabaseGetter(self.context).database()
            if db is None:
                raise Exception('Can\'t get parent database for %s' % self.context)
            for data in datas:
                try:
                    infos, ret, event = i.IDBPusher(db).push_event(data)
                    if event is not None: event.reindexObject()
                    messages.extend(infos)
                except Exception, e:
                    ret = 'failed'
                if ret == 'created':
                    created += 1
                elif ret == 'failed':
                    failed += 1
                elif ret == 'edited':
                    edited += 1
            # wehn we finally have added / edited, set the references
            for data in datas:
                pass
        except Exception, e:
            status = 0
            messages.append('%s' % e)
        messages.append('%s created, %s edited, %s failed' % (
            created, edited, failed))
        self.context.log(status=status, messages=messages)

class EventConstructor(grok.Adapter):
    grok.context(i.IDatabase)
    grok.provides(i.IEventConstructor)

    def construct(self, data):
        try:
            unique_SID_EID_check(self.context, data["sid"], data["eid"])
        except ActionExecutionError, e:
            raise NotUnique("%s_%s combination is not unique" % (
                data["sid"], data["eid"]))
        # get first a dummy event
        evt = createContentInContainer(self.context, 'libertic_event',
                                       title=data["title"])
        # then try to set all values
        i.IEventSetter(evt).set(data)
        return evt


class EventEditor(grok.Adapter):
    grok.context(i.IDatabaseItem)
    grok.provides(i.IEventEditor)

    def edit(self, data):
        db = i.IDatabaseGetter(self.context).database()
        evt = db.get_event(sid=data["sid"], eid=data["eid"]).getObject()
        try:
            editable_SID_EID_check(evt, data["sid"], data["eid"])
        except ActionExecutionError, e:
            raise NotUnique("%s_%s combination is not unique" % (
                data["sid"], data["eid"]))
        # we can edit an event only if it is not published
        wf = getToolByName(evt, 'portal_workflow')
        if wf.getInfoFor(evt, 'review_state') not in ['private', 'pending']:
            raise CantEdit("%s is not in pending state, cant edit" % evt)
        i.IEventSetter(evt).set(data)


class EventAdder(grok.Adapter):
    grok.context(i.IDatabaseItem)
    grok.provides(i.IEventAdder)


class EventSetter(grok.Adapter):
    grok.context(i.ILiberticEvent)
    grok.provides(i.IEventSetter)

    def set(self, data):
        for i in data:
            setattr(self.context, i, data[i])

class EventsGrabber(grok.GlobalUtility):
    grok.provides(i.IEventsGrabber)
    def fetch(self, url):
        dto = socket.getdefaulttimeout()
        contents = ''
        try:
            # never ever much timeout on sources
            socket.setdefaulttimeout(2)
            br = Browser.new(url)
            contents = br.contents
        finally:
            socket.setdefaulttimeout(dto)
        return contents

    def mappings(self, content):
        raise NotImplementedError()

    def validate(self, mappings):
        results = []
        for cdata in mappings:
            dm = getUtility(i.IEventDataManager)
            tdata = None
            errors = []
            # we accept to have one event
            # malformed, just skip it
            try:
                tdata = dm.validate(cdata)
                valid = True
            except schema.ValidationError, e:
                errors.append(e)
                tdata = None
            results.append(
                {
                    'initial': cdata,
                    'transformed': tdata,
                    'errors' : errors,
                })
        return results

    def data(self, url):
        contents = self.fetch(url)
        raw_mappings = self.mappings(contents)
        return self.validate(raw_mappings)


def as_unicode(mystr):
    ret = mystr
    if not isinstance(ret, unicode):
        try:
            ret = unicode(ret)
        except Exception, e:
            ret = ret.decode('utf-8')
    return ret


not_settable = ['contributors', 'creators', 'rights']
class EventDataManager(grok.GlobalUtility):
    grok.provides(i.IEventDataManager)

    def to_event_values(self, data):
        cdata = empty_data()
        for k in cdata.keys():
            cdata[k] = _marker
        # do not allow creators/contributors to be set
        for k in cdata.keys():
            if k in not_settable:
                del cdata[k]
        # keep only desired values settable on a liberticevent
        for k in data:
            if k in cdata:
                cdata[k] = data[k]
        # keep only setted data
        for k in cdata.keys():
            if cdata[k] is _marker:
                del cdata[k]
        # ensure tuples
        for k in ['target', 'subject', 'contained', 'related']:
            if isinstance(cdata.get(k, None), list):
                cdata[k] = tuple(cdata[k])
            if k in cdata:
                if not cdata[k]:
                    cdata[k] = tuple()
        # those fields are synonyms target/targets subject/subjects
        for k in ['subject', 'target']:
            if k in cdata:
                cdata[k+'s'] = cdata[k]
        for k in ['contained', 'related']:
            itms = []
            for itm in cdata[k]:
                if isinstance(itm, dict):
                    try:
                        sid = as_unicode(
                            itm['sid'])
                        eid = as_unicode(
                            itm['eid'])
                        it = SourceMapping(
                            sid, eid)
                        itms.append(it)
                    except Exception, e:
                        continue
            if itms:
                cdata[k] = tuple(itms)
        # defaults to fr
        if not cdata.get('language', None):
            cdata['language'] = 'fr'
        # bytesstrings, be sure not to be unicode
        for k in [
            u'source',
            u'video_url', u'gallery_url',
            u'photos2_url', u'audio_url',
            u'photos1_url', u'photos3_url',
            u'press_url']:
            if isinstance(cdata.get(k, None), unicode):
                try:
                    cdata[k] = cdata[k].encode('ascii')
                except:
                    cdata[k] = cdata[k].encode('utf-8')
        # date fields
        for k in [
            'event_start', 'event_end',
            'expires', 'effective',
        ]:
            val = cdata.get(k, None)
            if isinstance(val, basestring):
                try:
                    cdata[k] = datetime.datetime.strptime(
                        val, i.datefmt)
                except Exception, e:
                    pass
        return cdata

    def validate(self, data):
        cdata = self.to_event_values(data)
        obj = Dummy(**cdata)
        alsoProvides(obj , i.ILiberticEventMapping)
        errors = [a for a in
                  schema.getValidationErrors(i.ILiberticEventMapping, obj)
                  if not a[0] in not_settable]
        if errors:
            raise schema.ValidationError(errors)
        return cdata

class JSONGrabber(EventsGrabber):
    grok.name('json')
    def mappings(self, contents):
        results = []
        try:
            jdata = json.loads(contents)
        except Exception, e:
            raise Exception('Data is not in json format')
        try:
            results = jdata['events']
            if not isinstance(results, list):
                raise Exception()
        except Exception, e:
            raise Exception('Invalid json format, '
                            'not in the {"event": []} form')
        return results

# vim:set et sts=4 ts=4 tw=80:
