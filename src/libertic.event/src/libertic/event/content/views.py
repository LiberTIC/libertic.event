#!/usr/bin/env python
# -*- coding: utf-8 -*-
__docformat__ = 'restructuredtext en'
from five import grok
from zope import schema
from zope.interface import implements, alsoProvides, Interface

from plone.directives import form, dexterity
from z3c.form import button, field
from libertic.event import MessageFactory as _
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from libertic.event.content.liberticevent import (
    data_from_ctx,
)
from libertic.event.content.database import (
    IDatabase,
)
from Products.CMFCore.utils import getToolByName
from plone.app.collection.interfaces import ICollection
from Products.ATContentTypes.interfaces.topic import IATTopic
from libertic.event.content.liberticevent import export_csv

from libertic.event import interfaces as lei

try:
    import json
except ImportError:
    from simplejson import json


from libertic.event.utils import (
    ical_string,
    magicstring
)


class EventsSearch(grok.Adapter):
    grok.context(lei.IEventsCollection)
    grok.implements(lei.IEventsSearch)
    def search(self, **kwargs):
        sdata = []
        if IATTopic.providedBy(self.context):
            sdata = [a
                     for a in self.context.queryCatalog()
                     if a.portal_type in ['libertic_event']]
        if ICollection.providedBy(self.context):
            sdata = [a
                     for a in self.context.results(batch=False,
                                                   brains=True)
                     if a.portal_type in ['libertic_event']]
        if IDatabase.providedBy(self.context):
            catalog = getToolByName(self.context, 'portal_catalog')
            query = {
                'portal_type': 'libertic_event',
                'review_state': 'published',
                'path':  {
                    'query' : '/'.join(self.context.getPhysicalPath()),
                },
            }
            query.update(kwargs)
            sdata = catalog.searchResults(**query)
        return sdata

class EventsViewMixin(grok.View):
    grok.require('libertic.eventsdatabase.View')
    grok.context(lei.IEventsCollection)
    grok.baseclass()

    @property
    def items(self):
        return lei.IEventsSearch(self.context).search(
            **getattr(self, 'search_params', {}))


class EventsAsXml(EventsViewMixin):
    events = ViewPageTemplateFile('views_templates/xml.pt')
    _macros = ViewPageTemplateFile('liberticevent_templates/xmacros.pt')
    @property
    def xmacros(self):
        return self._macros.macros

    def render(self):
        sdata = {'data': []}
        for i in self.items:
            sdata['data'].append(data_from_ctx(i.getObject()))
        resp = self.events(**sdata).encode('utf-8')
        self.request.response.setHeader('Content-Type','text/xml')
        self.request.response.addHeader(
            "Content-Disposition","filename=%s.xml" % (
                self.context.getId()))
        self.request.response.setHeader('Content-Length', len(resp))
        self.request.response.write(resp)


class EventsAsJson(EventsViewMixin):
    def render(self):
        sdata = {'events': []}
        for i in self.items:
            sdata['events'].append(data_from_ctx(i.getObject()))
        resp = json.dumps(sdata)
        self.request.response.setHeader('Content-Type','application/json')
        self.request.response.addHeader(
            "Content-Disposition","filename=%s.json" % (
                self.context.getId()))
        self.request.response.setHeader('Content-Length', len(resp))
        self.request.response.write(resp)


class EventsAsCsv(EventsViewMixin):
    def render(self):
        rows = []
        for ix in self.items:
            sdata = data_from_ctx(ix.getObject())
            for it in ['performers', 'subjects',
                       'related', 'contained']:
                values = []
                for item in sdata[it]:
                    val = item
                    if it in ['performers', 'subjects']:
                        if not val.strip():
                            # skip empty keywords
                            continue
                    if it in ['related', 'contained']:
                        val = '%s%s%s' % (
                            val['sid'], lei.SID_EID_SPLIT,
                            val['eid'])
                    values.append(val)
                sdata[it] = '|'.join(values)
            rows.append(sdata)
        if rows:
            titles = rows[0].keys()
            titles.sort()
            export_csv(self.request, titles, rows)

class EventsAsIcal(EventsViewMixin):
    def render(self):
        events = []
        for i in self.items:
            event = i.getObject()
            icalv = event.restrictedTraverse('@@ical')
            events.append(icalv.ical_event())
        resp = magicstring(ical_string(events))
        self.request.response.setHeader('Content-Type','text/calendar')
        self.request.response.addHeader(
            "Content-Disposition","filename=%s.ics" % (
                self.context.getId()))
        self.request.response.setHeader('Content-Length', len(resp))
        self.request.response.write(resp)


class IAdvancedexportFields(form.Schema):
    event_start = schema.Datetime(title=_("Date start"), required=False,)
    event_end   = schema.Datetime(title=_("Date end"), required=False,)
    format = schema.Choice(title=_("Format"), required=False, vocabulary="lev_formats")

class advanced_export(form.Form):
    """"""
    # This form is available at the site root only
    grok.require('libertic.eventsdatabase.View')
    grok.context(lei.IEventsCollection)
    fields = field.Fields(IAdvancedexportFields)
    ignoreContext = True

    def update(self):
        __ = self.context.translate
        self.description = __(_(
            'Choose the dates between which you want to export events'))
        super(advanced_export, self).update()

    @button.buttonAndHandler(u'Ok')
    def handleApply(self, action):
        data, errors = self.extractData()
        views = {
            'json': EventsAsJson,
            'xml': EventsAsXml,
            'ical': EventsAsIcal,
            'csv': EventsAsCsv,
        }
        if errors:
            self.status = self.formErrorsMessage
            return
        params = dict([(a, data[a])
                       for a in 'event_start', 'event_end'
                       if data[a]])
        params['review_state'] = 'published'
        export_type = data['format']
        if not export_type:
            export_type = 'json'
        if 'event_end' in params:
            params['event_end'] = {'query': params['event_end'],
                                   'range':'max'}
        if 'event_start' in params:
            params['event_start'] = {'query': params['event_start'],
                                     'range':'min'}
        view = views[export_type](self.context, self.request)
        view.search_params = params
        return view()

# vim:set et sts=4 ts=4 tw=80:
