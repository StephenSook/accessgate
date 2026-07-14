# [Understanding SC 1.2.5 Audio Description (Prerecorded) (Level AA)](https://w3.org/TR/WCAG22#audio-description-prerecorded)

## In Brief

- **Goal**
    - Videos can be played with audio descriptions.
- **What to do**
    - Provide a synchronized spoken description of the visual content in videos.
- **Why it's important**
    - People who cannot see or understand the visual content can hear about it while playing videos.

## Success Criterion (SC)

[Audio description](#dfn-audio-description) is provided for all [prerecorded](#dfn-prerecorded) [video](#dfn-video) content in [synchronized media](#dfn-synchronized-media) .

## Intent

The intent of this success criterion is to provide people who are blind or visually impaired access to the visual information in a synchronized media presentation in the same [human language](#dfn-human-language) as the video or page on which it appears. The audio description augments the audio portion of the presentation with the information needed when the video portion is not available. During existing pauses in dialogue, audio description provides information about actions, characters, scene changes, and on-screen text that are important and are not described or spoken in the main sound track.

Note

For 1.2.3, 1.2.5, and 1.2.7, if all of the important information in the video track is already conveyed in the audio track, no additional audio description is necessary.

1.2.3 Audio Description or Media Alternative (Prerecorded), 1.2.5 Audio Description (Prerecorded), and 1.2.8 Media Alternative (Prerecorded) overlap somewhat with each other. This is to give the author some choice at the minimum conformance level, and to provide additional requirements at higher levels. At Level A in Success Criterion 1.2.3, authors do have the choice of providing either an audio description or a full text alternative. If they wish to conform at Level AA, under Success Criterion 1.2.5 authors must provide an audio description - a requirement already met if they chose that alternative for 1.2.3, otherwise an additional requirement. At Level AAA under Success Criterion 1.2.8 they must provide an extended text description. This is an additional requirement if both 1.2.3 and 1.2.5 were met by providing an audio description only. If 1.2.3 was met, however, by providing a text description, and the 1.2.5 requirement for an audio description was met, then 1.2.8 does not add new requirements.

## Benefits

- People who are blind or have low vision as well as those with cognitive limitations who have difficulty interpreting visually what is happening benefit from audio description of visual information.

## Examples

- **A movie with audio description**
    - **Describer:** A title, "Teaching Evolution Case Studies. Bonnie Chen." A teacher shows photographs of birds with long, thin beaks. **Bonnie Chen:** "These photos were all taken at the Everglades." **Describer:** The teacher hands each student two flat, thin wooden sticks. **Bonnie Chen:** "Today you will pretend to be a species of wading bird that has a beak like this." **Describer:** The teacher holds two of the sticks to her mouth making the shape of a beak. Transcript of audio based on the first few minutes of " [Teaching Evolution Case Studies, Bonnie Chen](http://www.pbs.org/wgbh/evolution/educators/teachstuds/tvideos.html) " (copyright WGBH and Clear Blue Sky Productions, Inc.)

## Related Resources

Resources are for information purposes only, no endorsement implied.

- [Description of Visual Information](https://www.w3.org/WAI/media/av/description/) , in [Making Audio and Video Media Accessible](https://www.w3.org/WAI/media/av/) , W3C Web Accessibility Initiative (WAI)
- [GBH - Integrate audio descriptions into multimedia presentations using SMIL](https://www.wgbh.org/foundation/services/ncam/tools-resources/accessible-digital-media-guidelines-guideline-h-multimedia)
- [Standard Techniques in Audio Description](http://joeclark.org/access/description/ad-principles.html)
- [Synchronized Multimedia Integration Language (SMIL) 1.0](https://www.w3.org/TR/REC-smil/)
- [Synchronized Multimedia Integration Language (SMIL 2.0)](https://www.w3.org/TR/SMIL/)
- [Accessibility Features of SMIL](https://www.w3.org/TR/SMIL-access/)

## Techniques

Each numbered item in this section represents a technique or combination of techniques that the Accessibility Guidelines Working Group deems sufficient for meeting this success criterion. A technique may go beyond the minimum requirement of the criterion. There may be other ways of meeting the criterion not covered by these techniques. For information on using other techniques, see [Understanding Techniques for WCAG Success Criteria](understanding-techniques) , particularly the "Other Techniques" section.

### Sufficient Techniques

- [G78: Providing a second, user-selectable, audio track that includes audio descriptions](https://www.w3.org/WAI/WCAG22/Techniques/general/G78)
- [G173: Providing a version of a movie with audio descriptions](https://www.w3.org/WAI/WCAG22/Techniques/general/G173) using one or more of the following techniques:
    - [SM6: Providing audio description in SMIL 1.0](https://www.w3.org/WAI/WCAG22/Techniques/smil/SM6)
    - [SM7: Providing audio description in SMIL 2.0](https://www.w3.org/WAI/WCAG22/Techniques/smil/SM7)
    - [G226: Providing audio descriptions by incorporating narration in the soundtrack](https://www.w3.org/WAI/WCAG22/Techniques/general/G226)
- [G8: Providing a movie with extended audio descriptions](https://www.w3.org/WAI/WCAG22/Techniques/general/G8) using one of the following techniques:
    - [SM1: Adding extended audio description in SMIL 1.0](https://www.w3.org/WAI/WCAG22/Techniques/smil/SM1)
    - [SM2: Adding extended audio description in SMIL 2.0](https://www.w3.org/WAI/WCAG22/Techniques/smil/SM2)
- [G203: Using a static text alternative to describe a talking head video](https://www.w3.org/WAI/WCAG22/Techniques/general/G203)

### Advisory Techniques

Although not required for conformance, the following additional techniques should be considered in order to make content more accessible. Not all techniques can be used or would be effective in all situations.

- [H96: Using the track element to provide audio descriptions](https://www.w3.org/WAI/WCAG22/Techniques/html/H96)

### Failures

The following are common mistakes that are considered failures of this success criterion by the Accessibility Guidelines Working Group.

- [F113: Failure of Success Criterion 1.2.5 due to not using available pauses in dialogue to provide audio descriptions of important visual content](https://www.w3.org/WAI/WCAG22/Techniques/failures/F113)

Key Terms

- **audio**
    - the technology of sound reproduction Note Audio can be created synthetically (including speech synthesis), recorded from real world sounds, or both.
- **audio description**
    - narration added to the soundtrack to describe important visual details that cannot be understood from the main soundtrack alone Note 1 Audio description of [video](#dfn-video) provides information about actions, characters, scene changes, on-screen text, and other visual content. Note 2 In standard audio description, narration is added during existing pauses in dialogue. (See also [extended audio description](#dfn-extended-audio-description) .) Note 3 Where all of the [video](#dfn-video) information is already provided in existing [audio](#dfn-audio) , no additional audio description is necessary. Note 4 Also called "video description" and "descriptive narration."
- **extended audio description**
    - audio description that is added to an audiovisual presentation by pausing the [video](#dfn-video) so that there is time to add additional description Note This technique is only used when the sense of the [video](#dfn-video) would be lost without the additional [audio description](#dfn-audio-description) and the pauses between dialogue/narration are too short.
- **human language**
    - language that is spoken, written or signed (through visual or tactile means) to communicate with humans Note See also [sign language](#dfn-sign-language) .
- **live**
    - information captured from a real-world event and transmitted to the receiver with no more than a broadcast delay Note 1 A broadcast delay is a short (usually automated) delay, for example used in order to give the broadcaster time to cue or censor the audio (or video) feed, but not sufficient to allow significant editing. Note 2 If information is completely computer generated, it is not live.
- **media alternative for text**
    - media that presents no more information than is already presented in text (directly or via text alternatives) Note A media alternative for text is provided for those who benefit from alternate representations of text. Media alternatives for text may be audio-only, video-only (including sign-language video), or audio-video.
- **prerecorded**
    - information that is not [live](#dfn-live)
- **sign language**
    - a language using combinations of movements of the hands and arms, facial expressions, or body positions to convey meaning
- **synchronized media**
    - [audio](#dfn-audio) or [video](#dfn-video) synchronized with another format for presenting information and/or with time-based interactive components, unless the media is a [media alternative for text](#dfn-media-alternative-for-text) that is clearly labeled as such
- **video**
    - the technology of moving or sequenced pictures or images Note Video can be made up of animated or photographic images, or both.

## Test Rules

The following are Test Rules for certain aspects of this Success Criterion. It is not necessary to use these particular Test Rules to check for conformance with WCAG, but they are defined and approved test methods. For information on using Test Rules, see [Understanding Test Rules for WCAG Success Criteria](understanding-act-rules.html) .

- [Video element visual content has accessible alternative](/WAI/standards-guidelines/act/rules/c5a4ea/proposed)
- [Video element visual content has strict accessible alternative](/WAI/standards-guidelines/act/rules/1ec09b/proposed)

[Back to Top](#top)

## Help improve this page

Please share your ideas, suggestions, or comments via email to the publicly-archived list [public-agwg-comments@w3.org](mailto:public-agwg-comments@w3.org?subject=%5BUnderstanding%20and%20Techniques%20Feedback%5D) or via GitHub

[Email](mailto:public-agwg-comments@w3.org?subject=%5BUnderstanding%20and%20Techniques%20Feedback%5D) [Fork &amp; Edit on GitHub](https://github.com/w3c/wcag/edit/main/understanding/20/audio-description-prerecorded.html) [New GitHub Issue](https://github.com/w3c/wcag/issues/new)